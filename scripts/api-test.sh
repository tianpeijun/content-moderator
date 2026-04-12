#!/usr/bin/env bash
# ============================================================
# api-test.sh
# 商城评论内容审核系统 — API 集成测试脚本
#
# 用法:
#   ./scripts/api-test.sh
#
# 环境变量（可选，不设置则使用默认值）:
#   API_URL    — API Gateway 端点
#   API_KEY    — X-API-Key 值
# ============================================================
set -uo pipefail

API="${API_URL:-https://YOUR_API_GATEWAY_ID.execute-api.us-east-1.amazonaws.com/prod}"
KEY="${API_KEY:-YOUR_API_KEY_HERE}"

PASS=0
FAIL=0
TOTAL=0
RESULTS=()

# ── 辅助函数 ─────────────────────────────────────────────────

call_api() {
  local desc="$1"
  local expected_http="$2"
  local expected_result="$3"  # pass/reject/flag/review/any/none
  shift 3
  TOTAL=$((TOTAL + 1))

  local response http_code body
  response=$(curl -s --max-time 120 -w "\n__HTTP_CODE__%{http_code}" "$@")
  http_code=$(echo "$response" | grep "__HTTP_CODE__" | sed 's/__HTTP_CODE__//')
  body=$(echo "$response" | grep -v "__HTTP_CODE__")

  local result confidence matched_rules status_text
  result=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',''))" 2>/dev/null || echo "")
  confidence=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('confidence',''))" 2>/dev/null || echo "")
  matched_rules=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('matched_rules',[])))" 2>/dev/null || echo "0")

  local ok=true
  # 检查 HTTP 状态码
  if [ "$http_code" != "$expected_http" ]; then
    ok=false
  fi
  # 检查审核结果
  if [ "$expected_result" != "any" ] && [ "$expected_result" != "none" ]; then
    if [ "$result" != "$expected_result" ]; then
      # 对于违规内容，reject 和 flag 都算通过
      if [ "$expected_result" = "reject_or_flag" ]; then
        if [ "$result" != "reject" ] && [ "$result" != "flag" ]; then
          ok=false
        fi
      else
        ok=false
      fi
    fi
  fi

  if [ "$ok" = true ]; then
    PASS=$((PASS + 1))
    status_text="✅ PASS"
  else
    FAIL=$((FAIL + 1))
    status_text="❌ FAIL"
  fi

  RESULTS+=("$status_text | $desc | HTTP=$http_code result=$result confidence=$confidence matched_rules=$matched_rules")
  echo "$status_text  $desc  [HTTP=$http_code result=$result confidence=$confidence rules=$matched_rules]"
}

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   商城评论内容审核系统 — API 集成测试                      ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  API: $API"
echo "║  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 一、多语种正常评论 ───────────────────────────────────────

echo "━━━ 一、多语种正常评论 ━━━"

call_api "T1 中文正常评论" "200" "pass" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"这个产品质量很好，物流也很快，推荐购买！","business_type":"商品评论"}'

call_api "T2 英文正常评论" "200" "pass" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"Great product! Fast shipping and excellent quality. Highly recommended.","business_type":"商品评论"}'

call_api "T3 日文正常评论" "200" "pass" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"この商品はとても良いです。品質が高く、配送も早かったです。おすすめします。","business_type":"商品评论"}'

call_api "T4 韩文正常评论" "200" "pass" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"이 제품은 정말 좋습니다. 품질이 우수하고 배송도 빠릅니다. 추천합니다.","business_type":"商品评论"}'

call_api "T5 法文正常评论" "200" "pass" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"Produit excellent ! Livraison rapide et qualité supérieure. Je recommande vivement.","business_type":"商品评论"}'

call_api "T6 俄文正常评论" "200" "pass" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"Отличный товар! Быстрая доставка и высокое качество. Рекомендую!","business_type":"商品评论"}'

call_api "T7 阿拉伯文正常评论" "200" "pass" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"منتج ممتاز! شحن سريع وجودة عالية. أنصح بشرائه بشدة.","business_type":"商品评论"}'

call_api "T8 中英混合评论" "200" "pass" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"中英混合评论 This product is amazing! 质量非常好 very durable 推荐购买","business_type":"商品评论"}'

echo ""

# ── 二、多语种违规内容 ───────────────────────────────────────

echo "━━━ 二、多语种违规内容 ━━━"

call_api "T9  中文违规(欺诈+隐私)" "200" "reject_or_flag" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"这个卖家是骗子！都是假货，加我微信xxx一起维权举报","business_type":"商品评论"}'

call_api "T10 英文违规(欺诈+隐私)" "200" "reject_or_flag" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"This product is a scam! Contact me at fake@email.com to file complaints together.","business_type":"商品评论"}'

call_api "T11 日文违规(欺诈+电话)" "200" "reject_or_flag" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"この商品を買うな！詐欺だ！販売者の電話番号は090-xxxx-xxxxです。みんなで通報しましょう！","business_type":"商品评论"}'

call_api "T12 韩文违规(欺诈+电话)" "200" "reject_or_flag" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"이 판매자는 사기꾼입니다! 제 전화번호 010-xxxx-xxxx로 연락주세요. 같이 신고합시다!","business_type":"商品评论"}'

echo ""

# ── 三、图片审核 ─────────────────────────────────────────────

echo "━━━ 三、图片审核 ━━━"

call_api "T13 正常图片+正常文本" "200" "pass" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"这个商品外观很漂亮","image_url":"https://picsum.photos/id/1/200/200.jpg","business_type":"商品评论"}'

call_api "T14 违规图片+可疑文本" "200" "reject_or_flag" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"看这个图片里的联系方式，加我有优惠","image_url":"https://dummyimage.com/400x200/000/fff.png&text=WeChat:fake123+Call:13800138000+Buy+now+50%25+OFF","business_type":"商品评论"}'

echo ""

# ── 四、输入验证 ─────────────────────────────────────────────

echo "━━━ 四、输入验证 ━━━"

call_api "T15 空内容返回400" "400" "none" \
  -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"","image_url":""}'

call_api "T16 缺少API Key返回403" "403" "none" \
  -X POST "$API/api/v1/moderate" \
  -H "Content-Type: application/json" \
  -d '{"text":"test"}'

echo ""

# ── 五、异步查询 ─────────────────────────────────────────────

echo "━━━ 五、异步查询 ━━━"

# 先发一条审核获取 task_id
task_id=$(curl -s --max-time 120 -X POST "$API/api/v1/moderate" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"text":"查询测试用","business_type":"商品评论"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))" 2>/dev/null)

if [ -n "$task_id" ]; then
  call_api "T17 查询已有任务" "200" "any" \
    -X GET "$API/api/v1/moderate/$task_id" \
    -H "X-API-Key: $KEY"
else
  echo "⚠️  跳过 T17：无法获取 task_id"
  TOTAL=$((TOTAL + 1))
  FAIL=$((FAIL + 1))
  RESULTS+=("❌ FAIL | T17 查询已有任务 | 无法获取 task_id")
fi

call_api "T18 查询不存在任务返回404" "404" "none" \
  -X GET "$API/api/v1/moderate/nonexistent-task-id-12345" \
  -H "X-API-Key: $KEY"

echo ""

# ── 测试报告 ─────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    测试结果汇总                           ║"
echo "╠══════════════════════════════════════════════════════════╣"
for r in "${RESULTS[@]}"; do
  echo "║  $r"
done
echo "╠══════════════════════════════════════════════════════════╣"
printf "║  总计: %d 个测试, %d 通过, %d 失败\n" "$TOTAL" "$PASS" "$FAIL"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "⚠️  部分测试未通过，请检查上方详情。"
  exit 1
fi

echo "🎉 所有测试通过！"
exit 0
