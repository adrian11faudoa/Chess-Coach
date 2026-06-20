# ChessCoach Web — AWS Deployment Guide

A production-ready web version of ChessCoach. The PySide6 desktop UI is replaced
with a **FastAPI WebSocket backend** + **React/Tailwind frontend**, containerised
with Docker and deployed on AWS ECS Fargate.

```
Browser ──WS/HTTP──► ALB ──► ECS Fargate (Docker)
                               ├─ FastAPI (uvicorn)
                               ├─ Stockfish (apt package)
                               └─ SQLite on EFS
```

---

## Project Structure

```
chess_coach_web/
├── backend/
│   ├── main.py                      # FastAPI app, WebSocket routes, REST API
│   ├── requirements.txt
│   └── chess/                       # All chess logic (no UI deps)
│       ├── core/
│       │   ├── game_session.py      # Per-player game state (async, no Qt)
│       │   ├── game_manager.py      # Move rules, PGN/FEN, undo/redo
│       │   └── game_analyzer_async.py  # Post-game analysis (async)
│       ├── engine/
│       │   └── engine_manager.py    # Stockfish integration
│       ├── coach/
│       │   └── chess_coach_engine.py   # Tactical/strategic commentary
│       ├── openings/
│       │   └── opening_recognizer.py   # ECO opening database (500+)
│       ├── database/
│       │   └── db_manager.py        # SQLite persistence
│       └── utils/
│           ├── config.py            # Env-var aware config
│           └── logger.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # Main app, game state, WS integration
│   │   ├── hooks/useGameSocket.js   # WebSocket hook with auto-reconnect
│   │   └── components/
│   │       ├── ChessBoard.jsx       # Interactive board, drag-and-drop
│   │       ├── CoachPanel.jsx       # EvalBar + coaching comments
│   │       ├── SidePanels.jsx       # MoveList, OpeningPanel, AnalysisPanel
│   │       └── NewGameModal.jsx     # Game setup dialog
│   ├── package.json
│   ├── vite.config.js               # Proxy /api and /ws to backend in dev
│   └── tailwind.config.js
├── infra/
│   └── cloudformation.yml           # Full ECS Fargate + ALB + EFS stack
├── scripts/
│   └── deploy.sh                    # One-command deploy script
├── .github/workflows/
│   └── deploy.yml                   # CI/CD: test → build → push → deploy
├── Dockerfile                       # Multi-stage: Node build + Python runtime
├── docker-compose.yml               # Local development
└── .dockerignore
```

---

## WebSocket Protocol

Connect to `ws://<host>/ws/game/<session-id>`

### Client → Server

| type | fields | description |
|------|--------|-------------|
| `new_game` | `player_color` (1=W/0=B), `engine_elo`, `time_control`, `mode` | Start game |
| `move` | `from` (sq index), `to`, `promotion` | Play a move |
| `move_uci` | `uci` | Play move as UCI string |
| `undo` | — | Undo last move |
| `navigate` | `move_index` | Jump to position |
| `hint` | — | Request coaching hint |
| `resign` | — | Resign |
| `load_pgn` | `pgn` | Load PGN for analysis |
| `set_fen` | `fen` | Set position |
| `legal_moves` | `from_sq` (optional) | Query legal moves |
| `ping` | — | Keepalive |

### Server → Client

| type | key fields | description |
|------|-----------|-------------|
| `connected` | `session_id`, `engine_ready`, `fen` | On connect |
| `game_started` | `fen`, `player_color`, `engine_elo` | Game began |
| `move_played` | `san`, `uci`, `from_sq`, `to_sq`, `fen`, `is_engine` | Move executed |
| `engine_thinking` | `thinking` (bool) | Engine status |
| `analysis_update` | `evaluation`, `best_move`, `lines[]` | Engine analysis |
| `coach_comment` | `text`, `category` | Coaching message |
| `opening_detected` | `name`, `eco`, `description`, `typical_plans[]` | Opening ID |
| `game_over` | `result` (`1-0`/`0-1`/`½-½`), `reason` | Game ended |
| `legal_moves` | `moves[]` (UCI) | Response to query |
| `position_set` | `fen`, `move_index` | After navigate/undo |
| `game_saved` | `game_id` | After auto-save |
| `pong` | — | Keepalive response |

---

## REST API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/sessions` | Create session → `{session_id}` |
| GET | `/api/sessions/{id}/fen` | Current FEN |
| GET | `/api/sessions/{id}/moves` | Move history |
| GET | `/api/sessions/{id}/legal_moves?from_sq=N` | Legal moves |
| GET | `/api/engine/status` | Engine health |
| GET | `/api/games?limit=20&offset=0` | Game history |
| GET | `/api/games/{id}` | Single game + moves |
| GET | `/api/stats` | Player statistics |
| GET | `/api/stats/openings` | Per-opening stats |
| GET | `/api/puzzles/next?rating=1200` | Next puzzle |
| POST | `/api/puzzles/attempt` | Record puzzle result |
| GET | `/api/health` | Health check |

---

## Local Development

### Prerequisites
- Docker Desktop **or** Python 3.11+ and Node 20+
- Stockfish installed locally (for non-Docker dev)

### Option A — Docker Compose (recommended)

```bash
cd chess_coach_web
docker compose up --build
# → http://localhost:8000
```

### Option B — Run services separately

**Terminal 1 — Backend:**
```bash
cd chess_coach_web/backend
pip install -r requirements.txt
STOCKFISH_PATH=$(which stockfish) uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd chess_coach_web/frontend
npm install
npm run dev
# → http://localhost:5173  (proxies /api and /ws to :8000)
```

---

## AWS Deployment

### Prerequisites
- AWS CLI configured (`aws configure`)
- Docker installed
- An AWS account with permissions for: ECR, ECS, CloudFormation, ALB, EFS, IAM

### Step 1 — Create the CloudFormation stack (first time only)

```bash
# Find your VPC and subnet IDs
aws ec2 describe-vpcs --query "Vpcs[?IsDefault].VpcId" --output text
aws ec2 describe-subnets --filters "Name=defaultForAz,Values=true" \
    --query "Subnets[*].SubnetId" --output text

# Deploy the infrastructure
aws cloudformation deploy \
  --template-file infra/cloudformation.yml \
  --stack-name chesscoach \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    VpcId=vpc-XXXXXXXX \
    SubnetIds=subnet-XXXXXXXX,subnet-YYYYYYYY \
    ContainerImage=PLACEHOLDER
```

This creates:
- ECR repository for container images
- ECS Fargate cluster + service
- Application Load Balancer (HTTP/HTTPS)
- EFS file system for SQLite persistence
- CloudWatch log group
- All necessary IAM roles and security groups

### Step 2 — Build and deploy

```bash
cd chess_coach_web
chmod +x scripts/deploy.sh
AWS_REGION=us-east-1 ./scripts/deploy.sh
```

The script:
1. Authenticates to ECR
2. Builds the multi-stage Docker image (Node → Python)
3. Pushes the image to ECR
4. Forces a new ECS deployment
5. Waits for health checks to pass
6. Prints the live URL

### Step 3 — Add HTTPS (optional but recommended)

```bash
# Request a certificate in ACM (must be in same region as ALB)
CERT_ARN=$(aws acm request-certificate \
  --domain-name chess.yourdomain.com \
  --validation-method DNS \
  --query CertificateArn --output text)

# Update the stack with the certificate
aws cloudformation update-stack \
  --stack-name chesscoach \
  --use-previous-template \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=VpcId,UsePreviousValue=true \
    ParameterKey=SubnetIds,UsePreviousValue=true \
    ParameterKey=ContainerImage,UsePreviousValue=true \
    ParameterKey=CertificateArn,ParameterValue=$CERT_ARN
```

---

## CI/CD with GitHub Actions

### Setup

Add these secrets to your GitHub repo (`Settings → Secrets → Actions`):

| Secret | Value |
|--------|-------|
| `AWS_ACCESS_KEY_ID` | IAM user key with ECR/ECS/CloudFormation permissions |
| `AWS_SECRET_ACCESS_KEY` | Corresponding secret |

### Pipeline

On every push to `main`:
1. **test-backend** — syntax check + ruff lint all Python files
2. **build-frontend** — `npm run build`, upload artifact
3. **docker** — build multi-stage image, push to ECR with git SHA tag
4. **deploy** — force new ECS deployment, wait for stable, print URL

### IAM Policy for CI

Minimum permissions for the GitHub Actions IAM user:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecs:UpdateService",
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:DescribeStacks"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/chesscoach-*"
    }
  ]
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STOCKFISH_PATH` | auto-detect | Path to stockfish binary |
| `DB_PATH` | `~/.chesscoach/chesscoach.db` | SQLite database file |
| `DATA_DIR` | `~/.chesscoach` | Directory for data files |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `WORKERS` | `1` | Uvicorn worker count (keep 1 for WebSocket sessions) |
| `ENGINE_ELO` | `1500` | Default engine ELO |
| `ENGINE_THREADS` | `2` | Stockfish thread count |
| `ENGINE_HASH_MB` | `256` | Stockfish hash table size |

> ⚠️ **Workers must stay at 1** unless you add a shared session store (Redis).
> Each worker has its own in-memory session dict, so WebSocket reconnects
> must hit the same worker. The ALB is configured with sticky sessions (lb_cookie)
> to handle this correctly for a single-instance deployment.

---

## Scaling Considerations

For multi-instance deployments:

1. **Session storage** — Move `sessions` dict to Redis (`aioredis`)
2. **Database** — Migrate from SQLite to PostgreSQL (RDS)
3. **Engine pool** — Run one Stockfish process per worker, manage with a pool
4. **WebSocket scaling** — Use AWS API Gateway WebSocket API + Lambda for serverless

---

## Cost Estimate (AWS, us-east-1)

| Service | Config | $/month |
|---------|--------|---------|
| ECS Fargate | 0.5 vCPU / 1 GB, running 24/7 | ~$15 |
| ALB | 1 instance | ~$18 |
| EFS | < 1 GB storage | ~$0.30 |
| ECR | < 1 GB storage | ~$0.10 |
| CloudWatch Logs | 14-day retention | ~$1 |
| **Total** | | **~$35/month** |

For development/low-traffic, consider stopping the ECS service when not in use.

---

## Keyboard Shortcuts (Browser)

| Key | Action |
|-----|--------|
| `←` | Previous move |
| `→` | Next move |
| `Home` | Go to start |
| `End` | Go to end |
| `f` | Flip board |
