cd /opt/data1/public/software/systools/autonome
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000 &
cd /opt/data1/public/software/systools/autonome
cd frontend && pnpm dev -p 3001 &
wait
