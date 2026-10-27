/* DAIN frontend API configuration.
 * Public HTTPS origin of this repository's backend/ deployed on Vercel. Do not add /docs,
 * /health, or /submissions/verify; the app appends API paths itself.
 * Never place GROQ_API_KEY, TAVILY_API_KEY, database credentials, or other secrets here.
 */
window.DAIN_API_BASE = "https://dain-new.vercel.app";
