# 1. 使用 python:3-alpine 作为基础镜像
# alpine 镜像非常小巧，适合构建轻量级应用
FROM python:3-alpine

# (可选但推荐) 设置时区为中国上海，确保日志时间等正确
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录
WORKDIR /app

# 复制依赖文件。先复制这一个文件可以更好地利用 Docker 的层缓存机制
COPY requirements.txt .

# 2. 安装依赖
RUN pip3 install --no-cache-dir -r requirements.txt

# 3. 将所有项目文件复制到镜像的工作目录里
COPY ./bot.py /bot.py

# 设置容器启动时默认执行的命令
CMD ["python3", "/bot.py"]
