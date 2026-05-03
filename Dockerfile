FROM python:3.11-slim

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    libreoffice \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright 브라우저 설치 (동적 사이트 크롤링 시 필요)
RUN playwright install chromium --with-deps 2>/dev/null || true

# 소스 코드 복사
COPY . .

# 출력 디렉토리 생성
RUN mkdir -p output/documents output/drafts logs data

# 환경 변수 (docker run 시 -e 로 전달)
ENV OPENAI_API_KEY=""
ENV EMAIL_PASSWORD=""
ENV SLACK_WEBHOOK_URL=""
ENV TZ=Asia/Seoul

# 기본 실행 명령: 스케줄러 모드
CMD ["python", "main.py", "--schedule", "--now"]
