FROM golang:1.22 AS build

WORKDIR /src
RUN git clone --depth 1 https://github.com/veeainc/lobstertrap.git .
RUN go test ./...
RUN CGO_ENABLED=0 go build -o /out/lobstertrap .

FROM debian:bookworm-slim

COPY --from=build /out/lobstertrap /usr/local/bin/lobstertrap
ENTRYPOINT ["lobstertrap"]
