package main
import "testing"
// The same placeholder order should map to the same prepared statement values.
func TestPlaceholders(t *testing.T) {
    s:=Server{postgres:true}
    if got:=s.bind("WHERE x=? AND y=?");got!="WHERE x=$1 AND y=$2" {t.Fatalf("got %q",got)}
    if got:=(&Server{}).bind("x=?");got!="x=?" {t.Fatalf("got %q",got)}
}
