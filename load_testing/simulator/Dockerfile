FROM golang:1.23-alpine AS builder
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/load-simulator ./main.go

FROM alpine:3.21
RUN addgroup -S app && adduser -S -G app app
COPY --from=builder /out/load-simulator /usr/local/bin/load-simulator
USER app
EXPOSE 8099
ENTRYPOINT ["/usr/local/bin/load-simulator"]
