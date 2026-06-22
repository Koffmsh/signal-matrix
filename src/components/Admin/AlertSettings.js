import { useState, useEffect } from "react";
import { apiFetch } from "../../services/api";

// ── Styles ──────────────────────────────────────────────────────────────────
const mono = "'IBM Plex Mono', 'Courier New', monospace";

const S = {
  wrap:        { padding: "20px 24px", color: "#c8d8e8", fontFamily: mono, maxWidth: "720px" },
  section:     { border: "1px solid #1a2535", borderRadius: "3px", marginBottom: "18px", background: "#080f1a" },
  sectionHead: { padding: "10px 16px", borderBottom: "1px solid #1a2535", color: "#00e5a0", fontSize: "11px", letterSpacing: "0.14em" },
  body:        { padding: "16px" },
  row:         { display: "flex", alignItems: "center", gap: "12px", padding: "10px 0" },
  label:       { color: "#c8d8e8", fontSize: "12px", minWidth: "90px" },
  sublabel:    { color: "#8899aa", fontSize: "10px" },
  input:       { background: "#0a1828", border: "1px solid #0077ff", borderRadius: "2px", color: "#e8f4ff", padding: "6px 10px", fontSize: "12px", fontFamily: mono, outline: "none", width: "240px" },
  readonly:    { color: "#e8f4ff", fontSize: "12px" },
  alertRow:    { display: "flex", alignItems: "flex-start", gap: "12px", padding: "12px 0", borderBottom: "1px solid #0d1a2a" },
  alertLabel:  { color: "#c8d8e8", fontSize: "12px", fontWeight: 600 },
  alertDesc:   { color: "#c8d8e8", fontSize: "12px", marginTop: "4px", lineHeight: 1.55 },
  applyBtn:    { background: "#001a0e", border: "1px solid #00e5a0", borderRadius: "2px", color: "#00e5a0", padding: "9px 22px", fontSize: "11px", cursor: "pointer", fontFamily: mono, letterSpacing: "0.1em" },
  note:        { color: "#f0b429", fontSize: "9px", letterSpacing: "0.06em" },
};

// Accent checkbox — uses native input with accentColor for the system green.
function Check({ checked, onChange, disabled }) {
  return (
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={e => onChange(e.target.checked)}
      style={{ width: "15px", height: "15px", accentColor: "#00e5a0", cursor: disabled ? "not-allowed" : "pointer" }}
    />
  );
}

export default function AlertSettings() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [toast, setToast]     = useState(null);

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(null), 2400); };

  const load = () => {
    setLoading(true);
    apiFetch(`/api/alerts/my-settings`)
      .then(r => r ? r.json() : null)
      .then(d => { if (d) setData(d); })
      .catch(() => showToast("Failed to load settings"))
      .finally(() => setLoading(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const setField = (key, val) => setData(d => ({ ...d, [key]: val }));
  const setAlert = (alertKey, enabled) =>
    setData(d => ({ ...d, alerts: d.alerts.map(a => a.key === alertKey ? { ...a, enabled } : a) }));

  const apply = async () => {
    setSaving(true);
    try {
      const payload = {
        email_enabled: !!data.email_enabled,
        sms_enabled:   !!data.sms_enabled,
        phone:         data.phone || null,
        alerts:        Object.fromEntries(data.alerts.map(a => [a.key, !!a.enabled])),
      };
      const res = await apiFetch(`/api/alerts/my-settings`, { method: "PUT", body: JSON.stringify(payload) });
      if (!res) return;
      if (!res.ok) {
        let detail = "Save failed";
        try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
        showToast(detail);
        return;
      }
      showToast("Settings applied");
      load();
    } catch {
      showToast("Network error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div style={{ ...S.wrap, color: "#8899aa", fontSize: "11px" }}>LOADING…</div>;
  if (!data)   return <div style={{ ...S.wrap, color: "#ff4d6d", fontSize: "11px" }}>Could not load alert settings.</div>;

  return (
    <div style={S.wrap}>
      {/* ── Delivery destinations ─────────────────────────────────────────── */}
      <div style={S.section}>
        <div style={S.sectionHead}>DELIVERY</div>
        <div style={S.body}>
          {/* Email */}
          <div style={S.row}>
            <Check checked={!!data.email_enabled} onChange={v => setField("email_enabled", v)} />
            <span style={S.label}>Email</span>
            <span style={S.readonly}>{data.email}</span>
            <span style={S.sublabel}>(your account email)</span>
          </div>

          {/* Phone / SMS */}
          <div style={S.row}>
            <Check
              checked={!!data.sms_enabled}
              onChange={v => setField("sms_enabled", v)}
              disabled={data.sms_globally_disabled}
            />
            <span style={S.label}>SMS</span>
            <input
              style={S.input}
              placeholder="+14155551234"
              value={data.phone || ""}
              onChange={e => setField("phone", e.target.value)}
            />
            {data.sms_globally_disabled && (
              <span style={S.note}>⚠ SMS pending carrier registration</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Alerts ────────────────────────────────────────────────────────── */}
      <div style={S.section}>
        <div style={S.sectionHead}>ALERTS</div>
        <div style={S.body}>
          {data.alerts.map(a => (
            <div key={a.key} style={S.alertRow}>
              <div style={{ paddingTop: "1px" }}>
                <Check checked={!!a.enabled} onChange={v => setAlert(a.key, v)} />
              </div>
              <div>
                <div style={S.alertLabel}>{a.label}</div>
                <div style={S.alertDesc}>{a.description}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button style={{ ...S.applyBtn, opacity: saving ? 0.5 : 1 }} onClick={apply} disabled={saving}>
          {saving ? "APPLYING…" : "APPLY SETTINGS"}
        </button>
      </div>

      {toast && (
        <div style={{
          position: "fixed", bottom: "30px", left: "50%", transform: "translateX(-50%)",
          background: "#0e1424", border: "1px solid #1a3050", borderRadius: "3px",
          color: "#c8d8e8", padding: "10px 18px", fontSize: "11px",
          letterSpacing: "0.08em", zIndex: 1000,
        }}>{toast}</div>
      )}
    </div>
  );
}
