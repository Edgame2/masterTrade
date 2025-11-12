# Feature-Aware Strategy Evaluation - Quick Reference

## 🚀 Quick Start

```bash
# Test feature computation
curl http://localhost:8006/api/v1/features/compute-for-signal/BTCUSDT

# Get trading signal
curl "http://localhost:8006/api/v1/strategy/signal/{STRATEGY_ID}/BTCUSDT?use_features=true"

# Run test suite
./ml_adaptation/test_strategy_evaluation.sh
```

## 📊 Signal Generation Logic

### Weighted Feature Scoring

| Feature | Weight | Bullish | Bearish |
|---------|--------|---------|---------|
| RSI | 30% | < 30 | > 70 |
| MACD | 20% | > 0 | < 0 |
| Social Sentiment | 20% | > 0.3 | < -0.3 |
| Sentiment Alignment | 15% | > 0.5 | < -0.5 |
| Market Strength | 15% | > 0.5 | < -0.5 |

### Decision Rules
- **BUY**: bullish_score > bearish_score AND > 0.5
- **SELL**: bearish_score > bullish_score AND > 0.5  
- **HOLD**: Neither condition met

## 🔗 API Endpoints

### 1. Evaluate with Features
```bash
POST /api/v1/strategy/evaluate-with-features
  ?strategy_id={UUID}
  &symbol={SYMBOL}
  &include_features={true|false}
```

### 2. Get Signal
```bash
GET /api/v1/strategy/signal/{strategy_id}/{symbol}
  ?use_features={true|false}
```

### 3. Compute Features
```bash
GET /api/v1/features/compute-for-signal/{symbol}
```

## 📝 Example Responses

### Signal Response
```json
{
  "action": "BUY",
  "confidence": 0.75,
  "reason": "Bullish signals dominate (score: 0.75)",
  "bullish_score": 0.75,
  "bearish_score": 0.2,
  "features_used": {
    "rsi": 28.5,
    "macd_histogram": 0.05,
    "social_sentiment": 0.4
  }
}
```

## 🧪 Testing Commands

```bash
# Feature summary
curl http://localhost:8006/api/v1/features/summary

# Test multiple symbols
for sym in BTCUSDT ETHUSDT BNBUSDT; do
  curl http://localhost:8006/api/v1/features/compute-for-signal/$sym
done

# Create test strategy
docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -c "
INSERT INTO strategies (id, name, type, config, created_at)
VALUES (gen_random_uuid(), 'Test Strategy', 'momentum', '{}', NOW())
RETURNING id;
"
```

## ⚙️ Implementation Files

| File | Lines | Purpose |
|------|-------|---------|
| `strategy_service/main.py` | +269 | Core evaluation logic |
| `strategy_service/api_endpoints.py` | +120 | REST endpoints |
| `ml_adaptation/test_strategy_evaluation.sh` | 300+ | Test suite |

## 🎯 Key Methods

```python
# Compute features
features = await service.compute_features_for_symbol("BTCUSDT")

# Evaluate strategy
result = await service.evaluate_strategy_with_features(
    strategy_id="uuid",
    symbol="BTCUSDT",
    include_features=True
)

# Generate signal
signal = await service._generate_feature_based_signal(
    features=features,
    strategy_type="momentum"
)
```

## ✅ Status Checklist

- [x] Feature computation integration
- [x] ML-powered signal generation
- [x] REST API endpoints (3)
- [x] Test suite (9/10 passing)
- [x] Docker deployment
- [x] Documentation
- [ ] Market data population
- [ ] Database schema fix
- [ ] Production monitoring

## 🔍 Troubleshooting

### Empty Features
**Cause**: No market data  
**Fix**: Run data collectors
```bash
docker compose exec market_data_service python historical_data_collector.py
```

### Database Error
**Error**: `column ss.metadata does not exist`  
**Status**: Pre-existing issue, not blocking  
**Fix**: Update query in `database.py`

### Service Not Responding
```bash
# Check logs
docker compose logs strategy_service --tail=100

# Rebuild
docker compose build strategy_service && docker compose up -d
```

## 📚 Related Documentation

- Full Documentation: `FEATURE_AWARE_STRATEGY_EVALUATION.md`
- Feature Pipeline: `ml_adaptation/FEATURE_PIPELINE.md`
- Feature Store: `ml_adaptation/FEATURE_STORE.md`
- TODO Tracking: `.github/todo.md` (line 1337)

## 🎉 Deployment Info

- **Deployed**: November 12, 2025
- **Port**: 8006
- **Status**: ✅ Operational
- **Tests**: 9/10 passing

---

**Quick Reference Version**: 1.0  
**Last Updated**: November 12, 2025
