# Pure-Go SQLite driver avoids CGo in this educational image.
FROM golang:1.23-bookworm AS build
WORKDIR /app
COPY go-http/go.mod ./
RUN go mod download
COPY go-http/ ./
RUN CGO_ENABLED=0 go build -o /bin/northstar ./cmd/server
FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /bin/northstar /usr/local/bin/northstar
EXPOSE 8080
ENTRYPOINT ["northstar"]
