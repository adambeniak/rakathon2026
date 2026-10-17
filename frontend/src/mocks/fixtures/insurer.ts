// GET /api/insurer/analytics as the backend computes it: `insurer.json` is exported from
// `app.timeline.insurer_analytics` over `backend/app/seed/data/insurer_cohort.json` (a backend test keeps them equal).
// Regenerate: cd backend && uv run python -c "import json; from app.api.routes.insurer import _analytics;
//   print(json.dumps(_analytics().model_dump(mode='json'), ensure_ascii=False, indent=2))" > ../frontend/src/mocks/fixtures/insurer.json
import { insurerAnalytics } from '@/features/insurer/api'
import raw from './insurer.json'

export const INSURER_ANALYTICS = insurerAnalytics.parse(raw)
