/* DAIN frontend API configuration.
 * Public HTTPS origin of the deployed Render backend. Do not add /docs,
 * /health, or /submissions/verify; the app appends API paths itself.
 * Never place GROQ_API_KEY, TAVILY_API_KEY, database credentials, or other secrets here.
 */
window.DAIN_API_BASE = "https://dain-backend.onrender.com";
