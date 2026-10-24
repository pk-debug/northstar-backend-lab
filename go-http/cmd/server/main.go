// Package main implements the same Northstar learning contract in idiomatic Go.
// WHAT: REST/SQL; WHY: safe authoritative server state; WHO: demo mobile user;
// WHEN: on requests; WHERE: Go server + SQL database; HOW: transactions;
// HOW MUCH: uses free local SQLite or self-hosted PostgreSQL.
package main

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"example.com/northstar/go-http/internal/data"
	_ "github.com/jackc/pgx/v5/stdlib" // Registers the postgres-compatible pgx driver.
	_ "modernc.org/sqlite"             // Registers a pure-Go SQLite database/sql driver.
)

// Asset mirrors the frontend TypeScript shape; PriceCents never enters HTTP JSON.
type Asset struct {
	Symbol        string  `json:"symbol"`
	CompanyName   string  `json:"companyName"`
	Exchange      string  `json:"exchange"`
	Price         float64 `json:"price"`
	Change        float64 `json:"change"`
	ChangePercent float64 `json:"changePercent"`
	History       []int   `json:"history"`
	Category      string  `json:"category"`
	PriceCents    int64   `json:"-"`
}
type Position struct {
	Symbol      string  `json:"symbol"`
	Quantity    int64   `json:"quantity"`
	AverageCost float64 `json:"averageCost"`
}
type Order struct {
	ID        string  `json:"id"`
	Symbol    string  `json:"symbol"`
	Side      string  `json:"side"`
	Quantity  int64   `json:"quantity"`
	Price     float64 `json:"price"`
	CreatedAt string  `json:"createdAt"`
	Status    string  `json:"status"`
}
type OrderRequest struct {
	Symbol   string `json:"symbol"`
	Side     string `json:"side"`
	Quantity int64  `json:"quantity"`
}
type Server struct {
	db       *sql.DB
	postgres bool
	assets   []Asset
	index    json.RawMessage
	lookup   map[string]Asset
}

// bind converts positional SQLite '?' parameters into PostgreSQL's '$1' format.
func (s *Server) bind(query string) string {
	if !s.postgres {
		return query
	}
	i := 0
	return replacePlaceholders(query, &i)
}
func replacePlaceholders(query string, idx *int) string {
	var b strings.Builder
	for _, r := range query {
		if r == '?' {
			*idx++
			fmt.Fprintf(&b, "$%d", *idx)
		} else {
			b.WriteRune(r)
		}
	}
	return b.String()
}

// writeJSON consistently returns a real HTTP status plus JSON content type.
func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
func fail(w http.ResponseWriter, code int, message string) {
	writeJSON(w, code, map[string]any{"ok": false, "message": message})
}

// openDB selects either local embedded SQLite or managed/self-hosted PostgreSQL.
func openDB() (*sql.DB, bool, error) {
	url := os.Getenv("DATABASE_URL")
	pg := strings.HasPrefix(url, "postgres://") || strings.HasPrefix(url, "postgresql://")
	var db *sql.DB
	var err error
	if pg {
		db, err = sql.Open("pgx", url)
	} else {
		p := os.Getenv("SQLITE_PATH")
		if p == "" {
			p = "northstar.db"
		}
		db, err = sql.Open("sqlite", p)
	}
	if err != nil {
		return nil, pg, err
	}
	if pg {
		db.SetMaxOpenConns(10)
	} else {
		db.SetMaxOpenConns(1)
	} // SQLite: serialize write transactions.
	db.SetConnMaxLifetime(time.Hour)
	if err = db.Ping(); err != nil {
		return nil, pg, err
	}
	return db, pg, nil
}

// initialize creates an educational schema and reproduces mobile demo balances.
func (s *Server) initialize(ctx context.Context) error {
	ddl := []string{
		"CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY,cash_cents BIGINT NOT NULL CHECK(cash_cents>=0))",
		"CREATE TABLE IF NOT EXISTS positions(symbol VARCHAR(16) PRIMARY KEY,quantity INTEGER NOT NULL CHECK(quantity>0),average_cost_cents BIGINT NOT NULL)",
		"CREATE TABLE IF NOT EXISTS orders(id VARCHAR(64) PRIMARY KEY,idempotency_key VARCHAR(128) UNIQUE NOT NULL,symbol VARCHAR(16) NOT NULL,side VARCHAR(4) NOT NULL,quantity INTEGER NOT NULL,price_cents BIGINT NOT NULL,created_at VARCHAR(40) NOT NULL,status VARCHAR(16) NOT NULL)",
		"CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC)",
	}
	for _, statement := range ddl {
		if _, err := s.db.ExecContext(ctx, statement); err != nil {
			return err
		}
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var count int
	if err = tx.QueryRowContext(ctx, "SELECT COUNT(*) FROM accounts").Scan(&count); err != nil {
		return err
	}
	if count == 0 {
		if _, err = tx.ExecContext(ctx, "INSERT INTO accounts(id,cash_cents) VALUES(1,1245000)"); err != nil {
			return err
		}
		for _, v := range []struct {
			s    string
			q, a int64
		}{{"AAPL", 4, 18245}, {"MSFT", 2, 40220}, {"VOO", 3, 49410}} {
			if _, err = tx.ExecContext(ctx, s.bind("INSERT INTO positions(symbol,quantity,average_cost_cents) VALUES(?,?,?)"), v.s, v.q, v.a); err != nil {
				return err
			}
		}
	}
	return tx.Commit()
}

// handleAssets filters sample market in memory; persist only user-owned ledger.
func (s *Server) handleAssets(w http.ResponseWriter, r *http.Request) {
	q := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("q")))
	result := make([]Asset, 0)
	for _, a := range s.assets {
		if strings.Contains(strings.ToLower(a.Symbol), q) || strings.Contains(strings.ToLower(a.CompanyName), q) {
			result = append(result, a)
		}
	}
	writeJSON(w, 200, result)
}
func (s *Server) handleAsset(w http.ResponseWriter, r *http.Request) {
	a, ok := s.lookup[strings.ToUpper(r.PathValue("symbol"))]
	if !ok {
		fail(w, 404, "That asset is not available in the sample market.")
		return
	}
	writeJSON(w, 200, a)
}

// handlePortfolio computes mark-to-demo-quote value from persisted quantities.
func (s *Server) handlePortfolio(w http.ResponseWriter, r *http.Request) {
	var cash int64
	if err := s.db.QueryRowContext(r.Context(), "SELECT cash_cents FROM accounts WHERE id=1").Scan(&cash); err != nil {
		fail(w, 500, "Database read failed")
		return
	}
	rows, err := s.db.QueryContext(r.Context(), "SELECT symbol,quantity,average_cost_cents FROM positions ORDER BY symbol")
	if err != nil {
		fail(w, 500, "Database read failed")
		return
	}
	defer rows.Close()
	positions := []Position{}
	var value int64
	for rows.Next() {
		var sym string
		var q, avg int64
		if err = rows.Scan(&sym, &q, &avg); err != nil {
			fail(w, 500, "Database read failed")
			return
		}
		positions = append(positions, Position{sym, q, float64(avg) / 100})
		value += s.lookup[sym].PriceCents * q
	}
	if err = rows.Err(); err != nil {
		fail(w, 500, "Database read failed")
		return
	}
	writeJSON(w, 200, map[string]any{"cash": float64(cash) / 100, "positions": positions, "positionsValue": float64(value) / 100, "totalValue": float64(cash+value) / 100})
}

// scanOrder converts stable SQL fields to the client-facing order type.
func scanOrder(scan func(...any) error) (Order, string, error) {
	var o Order
	var key string
	var p int64
	err := scan(&o.ID, &key, &o.Symbol, &o.Side, &o.Quantity, &p, &o.CreatedAt, &o.Status)
	o.Price = float64(p) / 100
	return o, key, err
}
func (s *Server) handleOrders(w http.ResponseWriter, r *http.Request) {
	rows, err := s.db.QueryContext(r.Context(), "SELECT id,idempotency_key,symbol,side,quantity,price_cents,created_at,status FROM orders ORDER BY created_at DESC,id DESC")
	if err != nil {
		fail(w, 500, "Database read failed")
		return
	}
	defer rows.Close()
	result := []Order{}
	for rows.Next() {
		o, _, err := scanOrder(rows.Scan)
		if err != nil {
			fail(w, 500, "Database read failed")
			return
		}
		result = append(result, o)
	}
	if err = rows.Err(); err != nil {
		fail(w, 500, "Database read failed")
		return
	}
	writeJSON(w, 200, result)
}

var safeKey = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,128}$`)

// newID generates a random identifier. Never use timestamps as idempotency keys.
func newID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}

// handlePlaceOrder is the transaction boundary, not a real brokerage operation.
func (s *Server) handlePlaceOrder(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, 16384)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	var request OrderRequest
	if err := decoder.Decode(&request); err != nil {
		fail(w, 400, "Invalid order JSON")
		return
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		fail(w, 400, "Only one JSON object is allowed")
		return
	}
	request.Symbol = strings.ToUpper(strings.TrimSpace(request.Symbol))
	key := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if !safeKey.MatchString(key) {
		fail(w, 400, "Supply an Idempotency-Key of 1–128 safe characters.")
		return
	}
	if request.Quantity <= 0 || request.Quantity > 1000000 || (request.Side != "BUY" && request.Side != "SELL") {
		fail(w, 400, "Enter a positive whole-share quantity and BUY or SELL.")
		return
	}
	a, ok := s.lookup[request.Symbol]
	if !ok {
		fail(w, 404, "That asset is not available in the sample market.")
		return
	}
	ctx := r.Context()
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		fail(w, 500, "Could not begin transaction")
		return
	}
	defer tx.Rollback()
	lockSql := "SELECT cash_cents FROM accounts WHERE id=1"
	if s.postgres {
		lockSql += " FOR UPDATE"
	}
	var cash int64
	if err = tx.QueryRowContext(ctx, lockSql).Scan(&cash); err != nil {
		fail(w, 500, "Could not lock account")
		return
	}
	prior, keyFound, err := scanOrder(tx.QueryRowContext(ctx, s.bind("SELECT id,idempotency_key,symbol,side,quantity,price_cents,created_at,status FROM orders WHERE idempotency_key=?"), key).Scan)
	if err == nil {
		if keyFound != key || prior.Symbol != request.Symbol || prior.Side != request.Side || prior.Quantity != request.Quantity {
			fail(w, 409, "Idempotency-Key was already used for a different order.")
			return
		}
		writeJSON(w, 200, map[string]any{"ok": true, "order": prior})
		return
	}
	if !errors.Is(err, sql.ErrNoRows) {
		fail(w, 500, "Could not read previous order")
		return
	}
	var quantity, average int64
	err = tx.QueryRowContext(ctx, s.bind("SELECT quantity,average_cost_cents FROM positions WHERE symbol=?"), request.Symbol).Scan(&quantity, &average)
	hasPosition := err == nil
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		fail(w, 500, "Could not read holdings")
		return
	}
	amount := a.PriceCents * request.Quantity
	if request.Side == "BUY" && amount > cash {
		fail(w, 409, "There is not enough demo cash for this order.")
		return
	}
	if request.Side == "SELL" && (!hasPosition || quantity < request.Quantity) {
		fail(w, 409, "You do not own enough shares for this demo sale.")
		return
	}
	if request.Side == "BUY" {
		if hasPosition {
			newQ := quantity + request.Quantity
			newAvg := (average*quantity + amount + newQ/2) / newQ
			_, err = tx.ExecContext(ctx, s.bind("UPDATE positions SET quantity=?,average_cost_cents=? WHERE symbol=?"), newQ, newAvg, request.Symbol)
		} else {
			_, err = tx.ExecContext(ctx, s.bind("INSERT INTO positions(symbol,quantity,average_cost_cents) VALUES(?,?,?)"), request.Symbol, request.Quantity, a.PriceCents)
		}
		cash -= amount
	} else {
		if quantity == request.Quantity {
			_, err = tx.ExecContext(ctx, s.bind("DELETE FROM positions WHERE symbol=?"), request.Symbol)
		} else {
			_, err = tx.ExecContext(ctx, s.bind("UPDATE positions SET quantity=? WHERE symbol=?"), quantity-request.Quantity, request.Symbol)
		}
		cash += amount
	}
	if err != nil {
		fail(w, 500, "Could not update holdings")
		return
	}
	if _, err = tx.ExecContext(ctx, s.bind("UPDATE accounts SET cash_cents=? WHERE id=1"), cash); err != nil {
		fail(w, 500, "Could not update cash")
		return
	}
	order := Order{newID(), request.Symbol, request.Side, request.Quantity, float64(a.PriceCents) / 100, time.Now().UTC().Format(time.RFC3339Nano), "SIMULATED"}
	_, err = tx.ExecContext(ctx, s.bind("INSERT INTO orders(id,idempotency_key,symbol,side,quantity,price_cents,created_at,status) VALUES(?,?,?,?,?,?,?,?)"), order.ID, key, order.Symbol, order.Side, order.Quantity, a.PriceCents, order.CreatedAt, order.Status)
	if err != nil {
		fail(w, 500, "Could not save order")
		return
	}
	if err = tx.Commit(); err != nil {
		fail(w, 500, "Could not commit transaction")
		return
	}
	writeJSON(w, 201, map[string]any{"ok": true, "order": order})
}
func main() {
	db, pg, err := openDB()
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()
	var assets []Asset
	if err = json.Unmarshal(data.Assets, &assets); err != nil {
		log.Fatal(err)
	}
	s := &Server{db: db, postgres: pg, assets: assets, index: data.Indexes, lookup: map[string]Asset{}}
	for _, a := range assets {
		s.lookup[a.Symbol] = a
	}
	if err = s.initialize(context.Background()); err != nil {
		log.Fatal(err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, 200, map[string]string{"status": "ok", "service": "go-http"})
	})
	mux.HandleFunc("GET /api/v1/assets", s.handleAssets)
	mux.HandleFunc("GET /api/v1/assets/{symbol}", s.handleAsset)
	mux.HandleFunc("GET /api/v1/indexes", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(s.index)
	})
	mux.HandleFunc("GET /api/v1/portfolio", s.handlePortfolio)
	mux.HandleFunc("GET /api/v1/orders", s.handleOrders)
	mux.HandleFunc("POST /api/v1/orders", s.handlePlaceOrder)
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	if _, err := strconv.Atoi(port); err != nil {
		log.Fatal(err)
	}
	log.Println("Northstar Go listening on :" + port)
	log.Fatal(http.ListenAndServe(":"+port, localCORS(mux)))
}

// localCORS permits browser-based Expo testing from a few localhost dev origins.
// Native Android/iOS clients are not subject to browser CORS checks.
func localCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin == "http://localhost:8081" || origin == "http://localhost:19006" || origin == "http://localhost:3000" {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Vary", "Origin")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Idempotency-Key")
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}
