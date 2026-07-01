Okay, let's create the structure for this web page using HTML and Tailwind CSS, along with JavaScript for interaction with a hypothetical Python backend.

**Assumptions:**

1.  You have a Python backend running (e.g., using Flask or Django) that provides API endpoints for the required actions (fetching data, saving settings, starting/stopping tasks, etc.).
2.  You'll replace the placeholder API URLs in the JavaScript with your actual backend endpoints.
3.  For simplicity, this example uses the Tailwind CSS CDN. For production, you'd typically set up Tailwind using Node.js/npm.

**File Structure:**

```
your-project/
├── index.html
├── script.js
└── (optional) style.css  // For minor custom styles not covered by Tailwind
```

**Explanation:**

1.  **HTML (`index.html`):**
    * Sets up the basic HTML structure.
    * Includes Tailwind CSS via CDN.
    * Uses `div` containers and Tailwind utility classes (`container`, `grid`, `flex`, `p-*`, `m-*`, `border`, `rounded`, `bg-*`, `text-*`, etc.) to replicate the layout from the image.
    * Uses appropriate HTML form elements (`label`, `input`, `select`, `button`, `textarea`).
    * Assigns unique `id` attributes to elements that need to be accessed or manipulated by JavaScript.
    * The holdings table (`<table>`) has a `<thead>` and an empty `<tbody>` (`id="holdingsTableBody"`) which will be populated by JavaScript. A loading/error state is included.
    * The order log is a `textarea` (`id="orderLog"`) set to `readonly`. Loading/error states are included.
    * A dedicated `div` (`id="messageArea"`) is added at the top to display status messages (loading, errors, success).
    * Basic CSS is included in `<style>` for message boxes and textarea behavior.

2.  **JavaScript (`script.js`):**
    * **Configuration:** Defines API endpoints in `API_ENDPOINTS` for easy maintenance. Sets a `POLLING_INTERVAL`.
    * **DOM References:** Gets references to all necessary HTML elements using their IDs.
    * **Utility Functions:**
        * `showMessage`: Displays feedback messages in the `messageArea`.
        * `apiRequest`: A reusable `async` function to handle `Workspace` calls, including setting headers, stringifying JSON bodies, basic error handling, and logging requests/responses.
    * **UI Update Functions:**
        * `updateConfigForm`, `updateStatusDisplay`, `updateHoldingsTable`, `updateLogs`: These functions take data received from the backend and update the corresponding parts of the HTML.
        * `updateHoldingsTable` dynamically creates table rows (`<tr>`, `<td>`) based on the fetched holdings data. It includes logic for conditional styling (e.g., text color for profit/loss) and creates input fields within the table.
        * `addHoldingInputListeners` and `handleHoldingInputChange`: Added to demonstrate how you might handle changes to the input fields directly within the holdings table (e.g., to update buy/sell prices). This sends an update to a hypothetical backend endpoint.
    * **Data Fetching Functions:**
        * `WorkspaceConfig`, `WorkspaceStatus`, `WorkspaceHoldings`, `WorkspaceLogs`: `async` functions that call `apiRequest` to get data from specific endpoints and then call the appropriate UI update function. They include basic loading/error state management for table/log areas.
    * **Action Handlers:**
        * Functions like `handleToggleMonitor`, `handleSaveConfig`, `handleClearLogs`, `handleExecuteBuy` are triggered by button clicks.
        * They prepare data (if necessary), call the relevant API endpoint (usually POST), disable the button during the request, show loading messages, and update the UI or fetch fresh data upon completion.
        * `handleGenericAction` is used for simpler POST actions that follow a similar pattern.
    * **Polling:**
        * `startPolling`, `stopPolling`, `pollData`: Implement logic to periodically fetch data (`status`, `holdings`, `logs`) if monitoring is active. Polling is started/stopped based on the status received from `WorkspaceStatus`.
    * **Event Listeners:** Attaches the handler functions to the `click` events of the buttons. Adds a listener for the "Select All" checkbox.
    * **Initial Load:** Uses `DOMContentLoaded` to ensure the HTML is ready. `WorkspaceAllData` is called once to load the initial state of the dashboard.

**To Use:**

1.  Save the code as `index.html` and `script.js`.
2.  Replace `API_BASE_URL` and verify/adjust the paths in `API_ENDPOINTS` in `script.js` to match your actual Python backend URLs.
3.  Ensure your Python backend serves the expected JSON data structures for each endpoint. For example:
    * `/api/holdings` should return an array of objects, each representing a stock holding with properties like `code`, `name`, `changePercent`, `costPrice`, etc.
    * `/api/status` should return an object like `{ isMonitoring: true, account: { id: '...', availableBalance: ..., ... } }`. `isMonitoring` is a compatibility field for the global auto-operation switch (`ENABLE_AUTO_OPERATION`).
    * `/api/config` should return an object with keys matching the config input IDs.
    * POST endpoints should generally return a JSON object indicating success, e.g., `{ success: true, message: "Action completed" }`.
4.  Open `index.html` in your web browser. It will try to connect to your backend API to load data and enable interactions. Check the browser's developer console (F12) for logs and error messages.

---
好的，这是您提供的API端点摘要的Markdown格式版本：

# API Endpoint Summary for miniQMT Web Server

## 1. Configuration Management

**Endpoint:** `/api/config`

*   **Method:** POST
*   **Purpose:** To save the current configuration settings.
*   **Request Data (JSON):**
    ```json
    {
        "singleBuyAmount": 35000,
        "firstProfitSell": 5.00,
        "firstProfitSellEnabled": true,
        "stockGainSellPencent": 60.00,
        "firstProfitSellPencent": true, // Note: ID is firstProfitSellPencent, likely meant to enable stockGainSellPencent
        "allowBuy": true,
        "allowSell": true,
        "stopLossBuy": 5.00,
        "stopLossBuyEnabled": true,
        "stockStopLoss": 7.00,
        "StopLossEnabled": true,
        "singleStockMaxPosition": 70000,
        "totalMaxPosition": 400000,
        "totalAccounts": "127.0.0.1", // IP Address
        "connectPort": 5000,
        "globalAllowBuySell": true
    }
    ```
*   **Response Data (JSON):**
    ```json
    {
        "success": true,
        "message": "Configuration saved successfully."
    }
    ```

*   **Method:** GET
*   **Purpose:** To load/import previously saved configuration settings.
*   **Request Data:** None
*   **Response Data (JSON):** Same structure as the POST request data.
    ```json
    {
        "singleBuyAmount": 35000,
        // ... other config parameters
        "globalAllowBuySell": true
    }
    ```

## 2. Account Information

**Endpoint:** `/api/account_info`

*   **Method:** GET
*   **Purpose:** To fetch current account details (balance, assets, etc.).
*   **Request Data:** None
*   **Response Data (JSON):**
    ```json
    {
        "accountId": "USER123",
        "availableBalance": 150000.75,
        "maxHoldingValue": 300000, // This might be calculated or a setting
        "totalAssets": 385000.50,
        "last_update_timestamp": "2023-10-27 10:30:00"
    }
    ```

## 3. Monitoring Control

**Endpoint:** `/api/monitor/start`

*   **Method:** POST
*   **Purpose:** To turn on the global auto-operation switch (`ENABLE_AUTO_OPERATION`). The route name is kept for compatibility.
*   **Request Data:** (Optional) Could send current config if not assumed to be already set on the server.
*   **Response Data (JSON):**
    ```json
    {
        "status": "running",
        "message": "Global auto operation started successfully."
    }
    ```

**Endpoint:** `/api/monitor/stop`

*   **Method:** POST
*   **Purpose:** To turn off the global auto-operation switch (`ENABLE_AUTO_OPERATION`). The route name is kept for compatibility.
*   **Request Data:** None
*   **Response Data (JSON):**
    ```json
    {
        "status": "stopped",
        "message": "Global auto operation stopped successfully."
    }
    ```

**Endpoint:** `/api/monitor/status` (Alternative to separate start/stop, or for polling)

*   **Method:** GET
*   **Purpose:** To get the current status of the monitor.
*   **Request Data:** None
*   **Response Data (JSON):**
    ```json
    {
        "status": "running" // or "stopped", "initializing", "error"
    }
    ```

## 4. Holdings (Position) Management

**Endpoint:** `/api/holdings`

*   **Method:** GET
*   **Purpose:** To fetch the list of current stock holdings.
*   **Request Data:** None
*   **Response Data (JSON Array):**
    ```json
    [
        {
            "code": "600000",
            "name": "浦发银行",
            "change_percent": 1.25, // Current day's price change %
            "current_price": 7.50,
            "cost_price": 7.20,
            "profit_loss_percent": 4.17, // (current_price - cost_price) / cost_price * 100
            "position_qty": 1000, // 持仓数量
            "available_qty": 1000, // 可用数量 (for selling)
            "total_qty": 1000, // 总数 (might be same as position_qty)
            "profit_taken": false, // 是否已止盈过部分
            "highest_price_since_buy": 7.80,
            "dynamic_stop_loss_price": 7.00,
            "open_time": "2023-10-26 09:35:00", // 建仓时间
            "base_cost_price": 7.10 // 基准成本价 (e.g., after partial sells or for tracking initial buy)
        }
        // ... more holding objects
    ]
    ```

**Endpoint:** `/api/holdings/initialize`

*   **Method:** POST
*   **Purpose:** To initialize or refresh holdings data, possibly by fetching from the broker.
*   **Request Data:** None
*   **Response Data (JSON):**
    ```json
    {
        "success": true,
        "message": "Holdings initialized successfully.",
        "holdings": [ /* ... array of holding objects as above ... */ ]
    }
    ```

## 5. Trading Operations

**Endpoint:** `/api/trade/buy`

*   **Method:** POST
*   **Purpose:** To execute buy orders based on the selected strategy.
*   **Request Data (JSON):**
    ```json
    {
        "strategy": "random_pool", // Value from buyStrategy select
        "quantity": 1, // Number of stocks to buy
        "singleBuyAmount": 35000 // From config, or could be passed if dynamic
    }
    ```
*   **Response Data (JSON):**
    ```json
    {
        "success": true,
        "message": "Buy order(s) placed successfully for 1 stock(s).",
        "orders_placed": [
            { "code": "600001", "status": "success", "details": "Order ID XYZ" }
        ]
    }
    ```
*(Note: Selling operations might be handled by the monitor based on config, or there could be manual sell buttons/APIs not explicitly shown for individual stocks in this part of the UI, though `allowSell` implies sell functionality exists).*

## 6. Order Log

**Endpoint:** `/api/logs/orders`

*   **Method:** GET
*   **Purpose:** To fetch the trading/order log.
*   **Request Data:** None
*   **Response Data (JSON or Text):**
    *   As JSON Array:
        ```json
        [
            { "timestamp": "2023-10-27 10:35:00", "type": "BUY", "stock": "600000", "price": 7.50, "quantity": 100, "message": "Bought 100 shares of 600000 at 7.50" },
            { "timestamp": "2023-10-27 10:40:00", "type": "SELL", "stock": "000001", "price": 12.80, "quantity": 50, "message": "Sold 50 shares of 000001 at 12.80 (Profit Target)" }
        ]
        ```
    *   As pre-formatted Text (given the `<textarea>` and `white-space: pre-wrap`):
        ```text
        2023-10-27 10:35:00 [BUY] Stock: 600000, Price: 7.50, Qty: 100
        2023-10-27 10:40:00 [SELL] Stock: 000001, Price: 12.80, Qty: 50 (Profit Target)
        ```

**Endpoint:** `/api/logs/clear`

*   **Method:** POST
*   **Purpose:** To clear the order log.
*   **Request Data:** None
*   **Response Data (JSON):**
    ```json
    {
        "success": true,
        "message": "Order log cleared."
    }
    ```

## 7. Data Management

**Endpoint:** `/api/data/clear_current`

*   **Method:** POST
*   **Purpose:** To clear current session/runtime data (e.g., in-memory state on the server, not persistent historical data).
*   **Request Data:** None
*   **Response Data (JSON):**
    ```json
    {
        "success": true,
        "message": "Current data cleared."
    }
    ```

**Endpoint:** `/api/data/clear_trades`

*   **Method:** POST
*   **Purpose:** To clear historical buy/sell transaction data (potentially from a database or persistent storage).
*   **Request Data:** None
*   **Response Data (JSON):**
    ```json
    {
        "success": true,
        "message": "Buy/Sell data cleared."
    }
    ```

## 8. API Connection Status (for the trading API, not this web server)

**Endpoint:** `/api/connection_status` (or could be part of a WebSocket stream)

*   **Method:** GET
*   **Purpose:** To check the status of the connection to the underlying trading API/broker.
*   **Request Data:** None
*   **Response Data (JSON):**
    ```json
    {
        "connected": true, // or false
        "message": "API Connected" // or "API Disconnected", "Error: ..."
    }
    ```

## General Considerations:

*   **Authentication/Authorization:** Not explicitly shown, but a real application would likely require authentication for these APIs.
*   **Error Handling:** API responses should include appropriate HTTP status codes (e.g., 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 500 Internal Server Error) and error messages in the JSON response body.
*   **WebSocket:** For real-time updates (like order log, connection status, and potentially live updates to holdings), a WebSocket connection might be established.
    *   **WebSocket Endpoint (e.g.):** `ws://localhost:5000/ws`
    *   **Messages:** Server could push updates for logs, account info, holding changes, and connection status.

This summary should give you a good idea of the backend API structure that would support the functionality presented in your `index.html`.
