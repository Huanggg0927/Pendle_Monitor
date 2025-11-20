# Linebot - Flask - PendleAPI 結合的查詢機器人
import os
import json
import http.client
from flask import Flask, request, abort

# 引入 LINE 相關套件
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# --- LINE Bot 設定 ---
# 請務必從 LINE Developers 網站取得這些資訊
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

app = Flask(__name__)

# 初始化 LINE Bot API
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 新增功能：搜索所有市場並提取資訊 ---
def search_pendle_markets(search_term: str) -> str:
    """
    呼叫 /markets/all API，根據代幣名稱搜索相關市場，
    並提取 name, underlyingAsset, impliedApy (排除 Implied APY 為 0 的市場)。
    """
    API_HOST = "api-v2.pendle.finance"
    API_PATH = "/core/v1/markets/all"
    conn = None
    
    try:
        conn = http.client.HTTPSConnection(API_HOST)
        conn.request("GET", API_PATH)
        res = conn.getresponse()
        
        if res.status != 200:
            return f"❌ 市場列表查詢失敗，狀態碼: {res.status} {res.reason}"
        
        data = res.read()
        all_data = json.loads(data.decode("utf-8"))
        
        search_term_lower = search_term.lower()
        found_markets = []
        
        # 確保數據結構正確
        if 'markets' in all_data and isinstance(all_data['markets'], list):
            for market in all_data['markets']:
                market_name = market.get('name', '')
                
                # 步驟 1: 檢查名稱是否包含搜尋詞 (不區分大小寫)
                if search_term_lower in market_name.lower():
                    
                    # 獲取 impliedApy
                    details = market.get('details', {})
                    impliedApy = details.get('impliedApy', None) # 暫時設為 None
                    
                    # 步驟 2: 檢查 Implied APY 是否為 0
                    # 如果 impliedApy 是數字型態 (float/int)，且值不等於 0
                    if isinstance(impliedApy, (int, float)) and impliedApy != 0:
                        found_markets.append(market)
                    
                    # 可選: 如果 impliedApy 是 0 或找不到 (None)，則跳過該市場。

        if not found_markets:
            return f"🤷 找不到包含 '{search_term}' 的相關市場，或所有找到的市場 Implied APY 皆為 0。"

        # 格式化輸出結果
        output_message = f"🔎 找到 **{search_term}** 相關市場 ({len(found_markets)} 個):\n"
        output_message += "----------------------------------------\n"
        
        for i, market in enumerate(found_markets, 1):
            name = market.get('name', 'N/A')
            underlyingAsset = market.get('underlyingAsset', 'N/A')
            
            # impliedApy 位於 'details' 字典中
            details = market.get('details', {})
            impliedApy = details.get('impliedApy', 'N/A')
            
            # 格式化 APY 輸出 (此處 impliedApy 必定非 0)
            apy_display = "N/A"
            if isinstance(impliedApy, (int, float)):
                 apy_display = f"{impliedApy * 100:.2f}%"
            
            # 提取 chainId 供詳細查詢使用
            chainId = market.get('chainId', 'N/A')

            output_message += (
                f"#{i} Token : {name}\n"
                f"   - ChainID : {chainId}\n"
                f"   - impliedApy : {apy_display}\n"
                f"   - underlyingAsset : {underlyingAsset}\n"
                f"   - MarketAddress : {market.get('address', 'N/A')}\n"
            )
            output_message += "-----------------------------------------\n"

        return output_message

    except Exception as e:
        return f"🚨 搜尋市場時發生錯誤：{e}"
    finally:
        if conn:
            conn.close()

# --- 您的 API 核心邏輯 (將其封裝為一個函數) ---
def get_pendle_prices(chain_id: str, market: str) -> str:
    """根據 chain_id 和 market 取得 Pendle 的價格數據並格式化"""
    try:
        conn = http.client.HTTPSConnection("api-v2.pendle.finance")
        path = f"/core/v1/sdk/{chain_id}/markets/{market}/swapping-prices"
        conn.request("GET", path)
        res = conn.getresponse()
        
        if res.status == 200:
            data = res.read()
            data_dict = json.loads(data.decode("utf-8"))
            
            # 格式化回傳給用戶的訊息
            apy = data_dict.get('impliedApy', 0) * 100
            pt_rate = data_dict.get('underlyingTokenToPtRate', 0)
            
            # 建立一個易讀的文字訊息
            message = (
                f"🔗 市場數據查詢結果：\n"
                f"----------------------------------------\n"
                f"Chain ID: {chain_id}\n"
                f"Market ID: {market}\n"
                f"Implied APY: **{apy:.2f}%**\n"
                f"Underlying -> PT Rate: **{pt_rate:.4f}**\n"
            )
            return message
        else:
            return f"❌ API 查詢失敗，狀態碼: {res.status}。請檢查 Chain ID/Market ID 是否正確。"
    except Exception as e:
        return f"🚨 發生錯誤：{e}"
    finally:
        conn.close()

# --- LINE Webhook 接收點 ---
@app.route("/callback", methods=['POST'])
def callback():
    """處理 LINE 傳送過來的 Webhook 請求"""
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/secret.")
        abort(400)
    return 'OK'

# --- 處理文字訊息 (主要邏輯變動區塊) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """處理用戶傳送的文字訊息"""
    text = event.message.text.strip()
    result_message = ""
    
    parts = text.split()
    command = parts[0].lower() if parts else ''
    
    if command == 'search' and len(parts) >= 2:
        # 新增功能：代幣名稱搜尋
        search_term = " ".join(parts[1:]) # 允許代幣名稱包含空格 (儘管不太常見)
        result_message = search_pendle_markets(search_term)
        
    elif len(parts) == 2 and parts[0].isdigit():
        # 舊有功能：精確查詢 (Chain ID + Market Address)
        chain_id = parts[0]
        market = parts[1]
        result_message = get_pendle_prices(chain_id, market)
        
    elif command == 'help':
        result_message = (
            "🤖 Pendle Bot 指令清單：\n"
            "----------------------------------------\n"
            "1. **代幣市場搜索 (新功能)**：\n"
            "   輸入：`search [代幣名稱]`\n"
            "   範例：`search kaito`\n"
            "\n"
            "2. **精確價格查詢 (舊功能)**：\n"
            "   輸入：`[Chain ID] [Market Address]`\n"
            "   範例：`8453 0x53fb20ff03ef94ef224557cc6262e0f11c20f718`\n"
        )
    else:
        result_message = "輸入格式不正確。請輸入 'help' 查看指令清單。"
        
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=result_message)
    )

# if __name__ == "__main__":
#     # 預設在本機環境運行 (端口 8000)
#     port = int(os.environ.get('PORT', 8000))
#     app.run(host='0.0.0.0', port=port)