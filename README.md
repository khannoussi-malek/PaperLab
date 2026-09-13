# PaperLab

Local-first research reading tool.

```sh
cp .env.example .env
docker compose up -d --build          # db, redis, api (:8000), worker; api runs migrations on start
curl localhost:8000/api/health        # vector round-trip through ORM and raw SQL

curl -F file=@paper.pdf localhost:8000/api/papers        # upload -> ingest job
curl localhost:8000/api/papers                           # status: uploaded -> extracting -> chunking -> ready
curl "localhost:8000/api/papers/<id>/chunks?page=3"      # chunks with bboxes (PDF points, top-left origin)
curl -X POST localhost:8000/api/papers/<id>/reingest     # idempotent re-run, e.g. after changing chunking

cd backend && uv run pytest                              # unit tests
```
