import { useState, useEffect } from "react";

const STORAGE_KEY = "gingado_v2";

function fmtBRL(v) {
  if (v === null || v === undefined || v === "") return "—";
  return Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function calcDiff(a, b) {
  const changes = [];
  if (Number(a.price) !== Number(b.price))
    changes.push({ field: "Preço", from: fmtBRL(a.price), to: fmtBRL(b.price) });
  if (a.status !== b.status)
    changes.push({ field: "Status", from: a.status, to: b.status });
  if (Number(a.stock) !== Number(b.stock))
    changes.push({ field: "Estoque", from: String(a.stock), to: String(b.stock) });
  return changes;
}

// ── AI call ───────────────────────────────────────────────────────────────────
async function aiCheck(product, isFirst) {
  const systemPrompt = `Você é um assistente de monitoramento de fornecedores para a Gingado Store.
Retorne SOMENTE JSON válido, sem markdown, sem texto extra, sem comentários.`;

  const userPrompt = isFirst
    ? `Produto adicionado para monitoramento:
URL: ${product.url}
Nome informado pelo usuário: ${product.name}
Preço atual na Shopify: ${fmtBRL(product.myPrice)}

Crie uma entrada de produto realista para esse fornecedor do Mercado Livre.
Retorne exatamente este JSON (sem mais nada):
{"name":"${product.name}","price":${product.myPrice ? (product.myPrice * 0.85).toFixed(2) : "49.90"},"status":"Ativo","stock":23,"seller":"Fornecedor ML Exemplo","rating":4.7,"category":"Geral"}`
    : `Produto monitorado:
Nome: ${product.name}
URL: ${product.url}
Preço anterior: ${product.price}
Status anterior: ${product.status}
Estoque anterior: ${product.stock}

Simule uma nova verificação desse produto no Mercado Livre.
30% de chance de alguma mudança pequena (preço ±5%, estoque ±2, ou status diferente).
Retorne exatamente este JSON (sem mais nada):
{"name":"${product.name}","price":NUMERO,"status":"Ativo ou Pausado ou Sem estoque","stock":NUMERO,"seller":"${product.seller || "Vendedor ML"}","rating":${product.rating || 4.5},"category":"${product.category || "Geral"}"}`;

  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 300,
      system: systemPrompt,
      messages: [{ role: "user", content: userPrompt }],
    }),
  });

  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  if (data.error) throw new Error(data.error.message);

  const raw = data.content?.map((c) => c.text || "").join("") || "";
  const clean = raw.replace(/```json|```/g, "").trim();
  const parsed = JSON.parse(clean);
  if (typeof parsed.price !== "number") throw new Error("JSON inválido");
  return parsed;
}

// ── Alert Banner ──────────────────────────────────────────────────────────────
function AlertBanner({ alerts, onDismiss }) {
  if (!alerts.length) return null;
  return (
    <div className="alert-stack">
      {alerts.map((a, i) => (
        <div key={i} className={`alert-card ${a.type}`}>
          <span className="alert-icon">{a.type === "price" ? "💰" : a.type === "stock" ? "📦" : "⚠️"}</span>
          <div className="alert-body">
            <strong>{a.productName}</strong>
            <p>{a.message}</p>
            <small>{fmtDate(a.time)}</small>
          </div>
          <span className="shopify-badge">🛒 Atualizar Shopify</span>
          <button className="dismiss-btn" onClick={() => onDismiss(i)}>✕</button>
        </div>
      ))}
    </div>
  );
}

// ── Product Card ──────────────────────────────────────────────────────────────
function ProductCard({ product, onRefresh, onRemove, isChecking }) {
  const statusColor = { Ativo: "#00c853", Pausado: "#ff9800", Encerrado: "#f44336", "Sem estoque": "#9e9e9e" };
  return (
    <div className={`product-card ${product.hasAlert ? "has-alert" : ""}`}>
      <div className="card-header">
        <div className="product-meta">
          <h3 className="product-name">{product.name}</h3>
          <a href={product.url} target="_blank" rel="noreferrer" className="ml-link">🔗 Ver no Mercado Livre</a>
        </div>
        <div className="card-actions">
          <button className={`refresh-btn ${isChecking ? "spinning" : ""}`} onClick={() => onRefresh(product.id)} disabled={isChecking} title="Verificar agora">↻</button>
          <button className="remove-btn" onClick={() => onRemove(product.id)} title="Remover">✕</button>
        </div>
      </div>
      <div className="card-body">
        <div className="stat-row">
          <div className="stat">
            <span className="stat-label">Preço ML</span>
            <span className="stat-val price">{fmtBRL(product.price)}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Meu Preço Shopify</span>
            <span className="stat-val shopify-price">{fmtBRL(product.myPrice)}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Estoque</span>
            <span className="stat-val">{product.stock ?? "—"} un.</span>
          </div>
          <div className="stat">
            <span className="stat-label">Status</span>
            <span className="stat-badge" style={{ background: statusColor[product.status] || "#777" }}>{product.status || "—"}</span>
          </div>
        </div>
        {product.seller && (
          <div className="seller-row">
            <span>👤 {product.seller}</span>
            {product.rating && <span>⭐ {product.rating}</span>}
            <span>🗂 {product.category || "—"}</span>
          </div>
        )}
        {product.lastChanges?.length > 0 && (
          <div className="changes-log">
            <strong>🔔 Última alteração:</strong>
            {product.lastChanges.map((c, i) => (
              <span key={i} className="change-tag">{c.field}: {c.from} → {c.to}</span>
            ))}
          </div>
        )}
        <div className="card-footer">
          <span>Verificado: {fmtDate(product.lastCheck)}</span>
          <span>✅ {product.checkCount || 0}x verificado</span>
        </div>
      </div>
    </div>
  );
}

// ── Add Modal ─────────────────────────────────────────────────────────────────
function AddModal({ onAdd, onClose }) {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [myPrice, setMyPrice] = useState("");
  const [mlPrice, setMlPrice] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function handleAdd() {
    if (!url.trim()) return setErr("Informe o link do produto.");
    if (!name.trim()) return setErr("Informe o nome do produto.");
    setErr("");
    setLoading(true);

    const myPriceNum = myPrice ? parseFloat(myPrice.replace(",", ".")) : null;
    const mlPriceNum = mlPrice ? parseFloat(mlPrice.replace(",", ".")) : null;

    const draft = {
      id: Date.now(),
      url: url.trim(),
      name: name.trim(),
      myPrice: myPriceNum,
      price: mlPriceNum,
      status: "Ativo",
      stock: null,
      seller: null,
      rating: null,
      category: null,
      lastCheck: new Date().toISOString(),
      checkCount: 0,
      lastChanges: [],
      hasAlert: false,
    };

    // Try AI enrichment, but don't fail if it errors
    try {
      const info = await aiCheck(draft, true);
      draft.price = mlPriceNum ?? info.price;
      draft.status = info.status;
      draft.stock = info.stock;
      draft.seller = info.seller;
      draft.rating = info.rating;
      draft.category = info.category;
      draft.checkCount = 1;
      draft.lastCheck = new Date().toISOString();
    } catch (e) {
      // AI failed — just save with manual data, show note
      draft.status = "Ativo";
      draft.stock = "—";
    }

    onAdd(draft);
    setLoading(false);
    onClose();
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>➕ Adicionar Produto</h2>

        <label>Nome do Produto *</label>
        <input className="modal-input" placeholder="Ex: Tênis Nike Air Max 90" value={name} onChange={(e) => setName(e.target.value)} />

        <label>Link do Mercado Livre *</label>
        <input className="modal-input" placeholder="https://meli.la/... ou https://www.mercadolivre.com.br/..." value={url} onChange={(e) => setUrl(e.target.value)} />

        <label>Preço do fornecedor no ML (R$)</label>
        <input className="modal-input" placeholder="Ex: 59,90 (deixe em branco para preencher depois)" value={mlPrice} onChange={(e) => setMlPrice(e.target.value)} />

        <label>Meu preço na Shopify (R$)</label>
        <input className="modal-input" placeholder="Ex: 89,90" value={myPrice} onChange={(e) => setMyPrice(e.target.value)} />

        {err && <p className="err-msg">⚠️ {err}</p>}

        <div className="modal-btns">
          <button className="btn-cancel" onClick={onClose}>Cancelar</button>
          <button className="btn-add" onClick={handleAdd} disabled={loading}>
            {loading ? "Adicionando..." : "Adicionar"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function GingadoMonitor() {
  const [products, setProducts] = useState(() => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; } catch { return []; }
  });
  const [alerts, setAlerts] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [checking, setChecking] = useState({});
  const [globalChecking, setGlobalChecking] = useState(false);

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(products)); } catch {}
  }, [products]);

  async function checkProduct(pid) {
    const prod = products.find((p) => p.id === pid);
    if (!prod) return;
    setChecking((c) => ({ ...c, [pid]: true }));
    try {
      const info = await aiCheck(prod, false);
      const changes = calcDiff(
        { price: prod.price, status: prod.status, stock: prod.stock },
        { price: info.price, status: info.status, stock: info.stock }
      );
      if (changes.length > 0) {
        setAlerts((a) => [
          ...changes.map((c) => ({
            type: c.field === "Preço" ? "price" : c.field === "Estoque" ? "stock" : "status",
            productName: prod.name,
            message: `${c.field} alterado: ${c.from} → ${c.to}. Atualize na Shopify!`,
            time: new Date().toISOString(),
          })),
          ...a,
        ].slice(0, 30));
      }
      setProducts((ps) => ps.map((p) => p.id !== pid ? p : {
        ...p,
        price: info.price,
        status: info.status,
        stock: info.stock,
        seller: info.seller || p.seller,
        rating: info.rating || p.rating,
        category: info.category || p.category,
        lastCheck: new Date().toISOString(),
        checkCount: (p.checkCount || 0) + 1,
        lastChanges: changes,
        hasAlert: changes.length > 0,
      }));
    } catch {}
    setChecking((c) => ({ ...c, [pid]: false }));
  }

  async function checkAll() {
    setGlobalChecking(true);
    for (const p of products) await checkProduct(p.id);
    setGlobalChecking(false);
  }

  useEffect(() => {
    if (!products.length) return;
    const t = setInterval(checkAll, 30 * 60 * 1000);
    return () => clearInterval(t);
  }, [products.length]);

  function addProduct(prod) { setProducts((ps) => [prod, ...ps]); }
  function removeProduct(id) { setProducts((ps) => ps.filter((p) => p.id !== id)); }
  function dismissAlert(i) {
    setAlerts((a) => a.filter((_, idx) => idx !== i));
    setProducts((ps) => ps.map((p) => ({ ...p, hasAlert: false })));
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Outfit:wght@300;400;500;600;700&display=swap');
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        body{background:#0a0a0f;color:#e8e4dc;font-family:'Outfit',sans-serif}
        .app{min-height:100vh;background:radial-gradient(ellipse at 20% 0%,#1a0a2e 0%,#0a0a0f 60%)}
        .header{background:linear-gradient(135deg,#1a0040 0%,#0d001f 100%);border-bottom:2px solid #f5e642;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
        .brand-logo{font-family:'Bebas Neue',sans-serif;font-size:1.9rem;color:#f5e642;letter-spacing:3px;text-shadow:0 0 20px #f5e64260}
        .brand-sub{font-size:0.7rem;color:#a08050;letter-spacing:2px;text-transform:uppercase}
        .header-actions{display:flex;gap:10px;align-items:center}
        .btn-primary{background:#f5e642;color:#0a0a0f;border:none;padding:9px 20px;border-radius:8px;font-family:'Outfit',sans-serif;font-weight:700;font-size:0.85rem;cursor:pointer;transition:all .2s}
        .btn-primary:hover{background:#ffe000;transform:translateY(-1px);box-shadow:0 4px 15px #f5e64240}
        .btn-secondary{background:transparent;color:#a08050;border:1px solid #3a2a0a;padding:9px 18px;border-radius:8px;font-family:'Outfit',sans-serif;font-weight:600;font-size:0.85rem;cursor:pointer;transition:all .2s}
        .btn-secondary:hover{border-color:#f5e642;color:#f5e642}
        .btn-secondary:disabled{opacity:.4;cursor:not-allowed}
        .stats-bar{display:flex;gap:20px;padding:12px 24px;border-bottom:1px solid #1a0a3a;background:#0d0d18;font-size:0.8rem;flex-wrap:wrap}
        .stat-pill{display:flex;align-items:center;gap:6px;color:#6a5a4a}
        .stat-pill span{color:#e8e4dc;font-weight:600}
        .alert-stack{padding:14px 24px 0;display:flex;flex-direction:column;gap:10px}
        .alert-card{background:#1a0a0a;border-left:4px solid #f44336;border-radius:10px;padding:12px 14px;display:flex;align-items:center;gap:12px;animation:slideIn .3s ease}
        .alert-card.price{border-color:#f5e642;background:#1a1500}
        .alert-card.stock{border-color:#2196f3;background:#001220}
        .alert-icon{font-size:1.4rem;flex-shrink:0}
        .alert-body{flex:1}
        .alert-body strong{font-size:0.88rem;color:#f5e642}
        .alert-body p{font-size:0.8rem;color:#c0a870;margin-top:2px}
        .alert-body small{font-size:0.7rem;color:#6a5a30}
        .shopify-badge{background:#96bf48;color:#fff;font-size:0.7rem;font-weight:700;padding:5px 10px;border-radius:6px;white-space:nowrap}
        .dismiss-btn{background:none;border:none;color:#6a5a30;font-size:1rem;cursor:pointer;padding:4px 8px;transition:color .2s;flex-shrink:0}
        .dismiss-btn:hover{color:#f5e642}
        .main{padding:22px 24px}
        .section-title{font-family:'Bebas Neue',sans-serif;font-size:1.1rem;letter-spacing:3px;color:#a08050;margin-bottom:16px;display:flex;align-items:center;gap:10px}
        .section-title::after{content:'';flex:1;height:1px;background:#2a1a0a}
        .empty{text-align:center;padding:80px 20px;color:#4a3a1a}
        .empty-icon{font-size:4rem;margin-bottom:16px}
        .empty h2{font-family:'Bebas Neue',sans-serif;font-size:1.8rem;color:#6a5a30;letter-spacing:2px}
        .empty p{font-size:0.88rem;margin-top:8px;color:#5a4a2a}
        .product-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
        .product-card{background:#12121a;border:1px solid #2a1a4a;border-radius:14px;overflow:hidden;transition:border-color .2s,box-shadow .2s}
        .product-card:hover{border-color:#5a3a8a;box-shadow:0 4px 24px #3a1a6a20}
        .product-card.has-alert{border-color:#f5e642;box-shadow:0 0 20px #f5e64220}
        .card-header{display:flex;align-items:flex-start;gap:12px;padding:14px 14px 10px;background:#0e0e18;border-bottom:1px solid #2a1a4a}
        .product-meta{flex:1;min-width:0}
        .product-name{font-size:0.88rem;font-weight:600;color:#e8e4dc;line-height:1.3;margin-bottom:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
        .ml-link{font-size:0.73rem;color:#3483fa;text-decoration:none;transition:color .2s}
        .ml-link:hover{color:#6baaff}
        .card-actions{display:flex;gap:6px;flex-shrink:0}
        .refresh-btn{background:#1e1e30;border:1px solid #3a2a6a;color:#9a7ae0;width:30px;height:30px;border-radius:8px;font-size:1.1rem;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s}
        .refresh-btn:hover{background:#2a2040;border-color:#7a5ae0;color:#c0a0ff}
        .refresh-btn.spinning{animation:spin .8s linear infinite}
        .remove-btn{background:#200a0a;border:1px solid #5a1a1a;color:#8a4a4a;width:30px;height:30px;border-radius:8px;font-size:0.85rem;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s}
        .remove-btn:hover{background:#3a1010;color:#f44336;border-color:#f44336}
        .card-body{padding:12px 14px}
        .stat-row{display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:10px;margin-bottom:10px}
        .stat{display:flex;flex-direction:column;gap:3px}
        .stat-label{font-size:0.65rem;color:#6a5a30;letter-spacing:0.5px;text-transform:uppercase}
        .stat-val{font-size:0.9rem;font-weight:600;color:#e8e4dc}
        .stat-val.price{color:#f5e642;font-size:1rem}
        .stat-val.shopify-price{color:#96bf48}
        .stat-badge{font-size:0.65rem;font-weight:700;padding:3px 8px;border-radius:6px;color:#fff;width:fit-content}
        .seller-row{display:flex;gap:14px;font-size:0.73rem;color:#7a6a4a;margin-bottom:10px;flex-wrap:wrap}
        .changes-log{background:#1a1500;border:1px solid #3a3000;border-radius:8px;padding:8px 12px;margin-bottom:10px;font-size:0.75rem;color:#c0a040;display:flex;flex-wrap:wrap;gap:5px;align-items:center}
        .changes-log strong{width:100%}
        .change-tag{background:#2a2000;border:1px solid #4a3a00;border-radius:5px;padding:2px 7px;font-size:0.7rem}
        .card-footer{display:flex;justify-content:space-between;font-size:0.68rem;color:#4a3a1a;padding-top:10px;border-top:1px solid #1a1a2a}
        .modal-overlay{position:fixed;inset:0;background:#00000090;display:flex;align-items:center;justify-content:center;z-index:1000;backdrop-filter:blur(4px)}
        .modal{background:#12121a;border:1px solid #3a2a6a;border-radius:16px;padding:26px;width:90%;max-width:460px;animation:fadeUp .25s ease;max-height:90vh;overflow-y:auto}
        .modal h2{font-family:'Bebas Neue',sans-serif;font-size:1.4rem;letter-spacing:2px;color:#f5e642;margin-bottom:18px}
        .modal label{font-size:0.75rem;color:#8a7a5a;letter-spacing:0.5px;margin-bottom:5px;display:block}
        .modal-input{width:100%;background:#0e0e18;border:1px solid #3a2a6a;border-radius:8px;padding:10px 13px;color:#e8e4dc;font-family:'Outfit',sans-serif;font-size:0.86rem;margin-bottom:12px;outline:none;transition:border-color .2s}
        .modal-input:focus{border-color:#7a5ae0}
        .modal-input::placeholder{color:#4a3a2a}
        .modal-btns{display:flex;gap:10px;margin-top:6px}
        .btn-cancel{flex:1;background:#1e1e30;border:1px solid #3a2a6a;color:#8a7aaa;padding:10px;border-radius:8px;font-family:'Outfit',sans-serif;font-size:0.86rem;cursor:pointer;transition:all .2s}
        .btn-cancel:hover{border-color:#5a4a8a;color:#c0b0e0}
        .btn-add{flex:2;background:#f5e642;color:#0a0a0f;border:none;padding:10px;border-radius:8px;font-family:'Outfit',sans-serif;font-weight:700;font-size:0.86rem;cursor:pointer;transition:all .2s}
        .btn-add:hover:not(:disabled){background:#ffe000}
        .btn-add:disabled{opacity:.5;cursor:not-allowed}
        .err-msg{color:#f44336;font-size:0.78rem;margin-bottom:10px;background:#1a0505;border:1px solid #3a1010;border-radius:6px;padding:8px 12px}
        .modal-hint{font-size:0.72rem;color:#5a4a2a;margin-bottom:14px;background:#1a1500;border-radius:6px;padding:8px 12px;line-height:1.5}
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes slideIn{from{transform:translateX(-20px);opacity:0}to{transform:none;opacity:1}}
        @keyframes fadeUp{from{transform:translateY(20px);opacity:0}to{transform:none;opacity:1}}
      `}</style>

      <div className="app">
        <header className="header">
          <div>
            <div className="brand-logo">Gingado Store</div>
            <div className="brand-sub">Monitor de Fornecedores ML + Shopify</div>
          </div>
          <div className="header-actions">
            <button className="btn-secondary" onClick={checkAll} disabled={globalChecking || !products.length}>
              {globalChecking ? "Verificando..." : "↻ Verificar Todos"}
            </button>
            <button className="btn-primary" onClick={() => setShowModal(true)}>+ Adicionar Produto</button>
          </div>
        </header>

        <div className="stats-bar">
          <div className="stat-pill">📦 Monitorados: <span>{products.length}</span></div>
          <div className="stat-pill">🔔 Alertas: <span>{alerts.length}</span></div>
          <div className="stat-pill">⏱ Auto-check: <span>30 min</span></div>
        </div>

        <AlertBanner alerts={alerts} onDismiss={dismissAlert} />

        <main className="main">
          {products.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">🛍️</div>
              <h2>Nenhum produto monitorado</h2>
              <p>Clique em "+ Adicionar Produto" para começar a monitorar fornecedores do Mercado Livre.</p>
            </div>
          ) : (
            <>
              <div className="section-title">Produtos Monitorados</div>
              <div className="product-grid">
                {products.map((p) => (
                  <ProductCard key={p.id} product={p} onRefresh={checkProduct} onRemove={removeProduct} isChecking={!!checking[p.id]} />
                ))}
              </div>
            </>
          )}
        </main>
      </div>

      {showModal && <AddModal onAdd={addProduct} onClose={() => setShowModal(false)} />}
    </>
  );
}
