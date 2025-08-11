docker buildx build -f Dockerfile --platform linux/amd64,linux/arm64 -t heifeng/bwgbot:$(date +%Y%m%d_%H%M%S) -t heifeng/bwgbot:latest --push .
