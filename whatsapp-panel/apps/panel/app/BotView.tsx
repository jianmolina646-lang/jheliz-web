'use client';

import { FormEvent, useEffect, useState } from 'react';

type BotConfig = { name: string; prefix: string; welcomeMessage: string; enabled: boolean };

async function request(path: string, options?: RequestInit) {
  const response = await fetch(`/api${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!response.ok) throw new Error('REQUEST');
  return response.json();
}

export default function BotView() {
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    request('/bot/config').then(setConfig).catch(() => setMessage('No se pudo cargar la configuración.'));
  }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config) return;
    setSaving(true);
    setMessage('');
    try {
      const saved = await request('/bot/config', { method: 'PUT', body: JSON.stringify(config) });
      setConfig(saved);
      setMessage('Configuración guardada. Los cambios ya están activos.');
    } catch {
      setMessage('No se pudo guardar. Revisa los campos e intenta nuevamente.');
    } finally {
      setSaving(false);
    }
  }

  return <>
    <div className="title"><div><span className="eyebrow">CONFIGURACIÓN PRINCIPAL</span><h1>Tu bot de WhatsApp</h1><p>Administra el bot conectado sin crear sesiones duplicadas.</p></div></div>
    {!config ? <article className="placeholder"><span>⌘</span><h2>Cargando configuración…</h2></article> :
      <section className="bot-config-grid">
        <form className="bot-config-card" onSubmit={save}>
          <div className="card-head"><div><small>IDENTIDAD Y RESPUESTAS</small><h3>Configuración del bot</h3></div><label className="switch"><input type="checkbox" checked={config.enabled} onChange={e => setConfig({ ...config, enabled: e.target.checked })}/><span></span>{config.enabled ? 'Activo' : 'Pausado'}</label></div>
          <label>Nombre del bot<input value={config.name} maxLength={80} required onChange={e => setConfig({ ...config, name: e.target.value })}/></label>
          <label>Prefijo de comandos<input value={config.prefix} maxLength={3} required onChange={e => setConfig({ ...config, prefix: e.target.value.replace(/\s/g, '') })}/><small>Ejemplo: con “.” tus clientes escribirán .menu o .shop.</small></label>
          <label>Mensaje principal<textarea value={config.welcomeMessage} maxLength={2000} required rows={7} onChange={e => setConfig({ ...config, welcomeMessage: e.target.value })}/></label>
          {message && <div className={message.startsWith('Configuración') ? 'success-message' : 'form-error'}>{message}</div>}
          <button className="primary" disabled={saving}>{saving ? 'Guardando…' : 'Guardar configuración'}</button>
        </form>
        <article className="bot-preview"><span className="eyebrow">VISTA PREVIA</span><div className="phone-preview"><header><i>J</i><div><b>{config.name || 'Tu bot'}</b><small>{config.enabled ? 'en línea' : 'pausado'}</small></div></header><div className="chat-bubble">{config.welcomeMessage || 'Escribe el mensaje principal del bot.'}<time>ahora ✓✓</time></div><div className="command-preview">Prueba: <b>{config.prefix || '.'}menu</b></div></div></article>
      </section>}
  </>;
}
