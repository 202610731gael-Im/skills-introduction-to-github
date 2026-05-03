# 🤖 지원사업 공고 자동화 시스템

매일 아침 지정 사이트에서 지원사업 공고를 수집하고, 기업 적합도를 분석하여 **70% 이상**인 공고의 문서를 자동 다운로드하고 초안 파일을 생성해주는 업무 자동화 시스템입니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 🔍 **공고 수집** | 기업마당, K-스타트업 등 설정 사이트에서 매일 신규 공고 크롤링 |
| 📊 **적합성 분석** | 규칙 기반 점수 + GPT-4o LLM 분석으로 기업 적합도 0~100점 산출 |
| 📥 **문서 다운로드** | 70점 이상 공고의 PDF/HWP/DOCX 첨부파일 자동 다운로드 |
| 📝 **초안 생성** | 요약 브리핑·사업계획서 초안·체크리스트를 DOCX/MD 파일로 생성 |
| 📧 **알림 발송** | 결과를 이메일 HTML 보고서 또는 슬랙 메시지로 전송 |

---

## 프로젝트 구조

```
.
├── main.py                     # 메인 실행 파일 (스케줄러 포함)
├── config/
│   └── settings.yaml           # 전체 설정 (사이트, 기업 프로필, API 키 등)
├── src/
│   ├── crawler/
│   │   ├── base_crawler.py     # 크롤러 추상 기본 클래스 + Announcement 스키마
│   │   ├── bizinfo_crawler.py  # 기업마당 크롤러
│   │   ├── kstartup_crawler.py # K-스타트업 크롤러
│   │   ├── generic_crawler.py  # 범용 크롤러 (새 사이트 추가 시 사용)
│   │   └── crawler_factory.py  # 사이트 유형에 따른 크롤러 선택
│   ├── db/
│   │   └── database.py         # SQLite DB 관리 (중복 방지, 조회)
│   ├── scorer/
│   │   └── eligibility_scorer.py  # 규칙 기반 + LLM 적합성 분석기
│   ├── downloader/
│   │   └── document_fetcher.py # 첨부파일 다운로더
│   ├── generator/
│   │   └── draft_generator.py  # LLM 기반 초안 파일 생성기
│   └── notifier/
│       └── email_notifier.py   # 이메일 / 슬랙 알림
├── tests/
│   ├── test_scorer.py          # 적합성 분석기 단위 테스트
│   └── test_database.py        # DB 단위 테스트
├── output/
│   ├── documents/              # 다운로드된 첨부파일
│   └── drafts/                 # 생성된 초안 파일
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 빠른 시작

### 1. 환경 설정

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 OPENAI_API_KEY 등 입력
```

### 2. 기업 프로필 설정

`config/settings.yaml`에서 기업 정보를 입력합니다:

```yaml
company_profile:
  name: "우리 기업"
  industry: "IT서비스"
  employee_count: 15
  region: "서울"
  certifications:
    - "벤처기업확인"
  keywords:
    - "AI"
    - "디지털전환"
```

### 3. 실행

```bash
# 즉시 1회 실행
python main.py

# 매일 오전 7시 자동 실행 (스케줄러 모드)
python main.py --schedule

# 스케줄러 시작 + 즉시 1회 실행
python main.py --schedule --now
```

### 4. Docker로 실행

```bash
# 환경 변수 설정
cp .env.example .env  # .env 파일 편집

# 빌드 및 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

---

## 새 사이트 추가 방법

1. `src/crawler/` 에 새 크롤러 파일 생성 (`BaseCrawler` 상속)
2. `src/crawler/crawler_factory.py`의 `crawler_map`에 등록
3. `config/settings.yaml`의 `sites` 목록에 사이트 추가

```python
# 예: my_site_crawler.py
from .base_crawler import Announcement, BaseCrawler

class MySiteCrawler(BaseCrawler):
    def fetch_announcements(self): ...
    def fetch_detail(self, ann): ...
```

---

## 알림 설정

### 이메일 (Gmail)
```yaml
email:
  enabled: true
  sender: "your@gmail.com"
  recipients: ["team@company.com"]
```
Gmail 앱 비밀번호를 `EMAIL_PASSWORD` 환경 변수로 설정하세요.

### 슬랙
```yaml
slack:
  enabled: true
  webhook_url: ""  # SLACK_WEBHOOK_URL 환경변수 사용
```

---

## 기술 스택

- **크롤링**: `requests` + `BeautifulSoup4`
- **스케줄러**: `APScheduler`
- **DB**: `SQLite` (내장)
- **LLM 분석**: `OpenAI GPT-4o API`
- **문서 처리**: `pdfplumber`, `python-docx`
- **배포**: `Docker` + `docker-compose`
