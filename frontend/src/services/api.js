const BASE = '';

async function request(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, options);
  if (!res.ok) throw new Error(`API Error ${res.status}: ${res.statusText}`);
  return res.json();
}

function postJson(url, data) {
  return request(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}

// ── Characters ──
export const getCharacters = () => request('/api/rp/get_characters');
export const getCharacterDetail = (folderId) => request(`/api/rp/get_character_detail?folder_id=${encodeURIComponent(folderId)}`);
export const saveCharacter = (formData) => fetch(`${BASE}/api/rp/save_character`, { method: 'POST', body: formData }).then(r => r.json());
export const deleteCharacter = (charId) => postJson('/api/rp/delete_character', { character_id: charId });

// ── Users ──
export const getUsers = () => request('/api/rp/get_users');
export const getUserDetail = (id) => request(`/api/rp/get_user_detail?user_id=${encodeURIComponent(id)}`);
export const saveUser = (formData) => fetch(`${BASE}/api/rp/save_user`, { method: 'POST', body: formData }).then(r => r.json());
export const deleteUser = (userId) => postJson('/api/rp/delete_user', { user_id: userId });

// ── Chat ──
let _activeStreamController = null;

export function abortActiveStream() {
  if (_activeStreamController) {
    _activeStreamController.abort();
    _activeStreamController = null;
  }
}

export async function* chatStream(data) {
  // Cancel any previous active stream
  abortActiveStream();
  
  const controller = new AbortController();
  _activeStreamController = controller;
  
  // Safety timeout: 5 minutes max for entire stream
  const timeoutId = setTimeout(() => controller.abort(), 300000);
  
  try {
    const res = await fetch(`${BASE}/api/rp/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      signal: controller.signal,
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.trim()) {
          try { yield JSON.parse(line); } catch { /* skip malformed */ }
        }
      }
    }
    if (buffer.trim()) {
      try { yield JSON.parse(buffer); } catch { /* skip */ }
    }
  } finally {
    clearTimeout(timeoutId);
    if (_activeStreamController === controller) {
      _activeStreamController = null;
    }
  }
}

// ── History ──
export const getChatHistory = (charId, sessionId) => {
  let url = `/api/rp/history/${encodeURIComponent(charId)}`;
  if (sessionId) url += `?session_id=${encodeURIComponent(sessionId)}`;
  return request(url);
};
export const deleteMessage = (data) => postJson('/api/rp/delete_message', data);
export const getHistorySessions = (charId) => request(`/api/rp/get_history_sessions?char_id=${encodeURIComponent(charId)}`);
export const deleteHistorySession = (data) => postJson('/api/rp/delete_history_session', data);

// ── Files ──
export const uploadFile = (formData) => fetch(`${BASE}/api/rp/upload_file`, { method: 'POST', body: formData }).then(r => r.json());

// ── Instructions ──
export const getInstructions = () => request('/api/rp/get_instructions');
export const getInstructionContent = (name) => request(`/api/rp/get_instruction_content?name=${encodeURIComponent(name)}`);
export const saveInstruction = (data) => postJson('/api/shared/save_instruction', data);

// ── Settings (API Keys) ──
export const getApiKeys = () => request('/api/rp/settings/api_keys');
export const addApiKey = (data) => postJson('/api/rp/settings/api_key', data);
export const editApiKey = (data) => postJson('/api/rp/settings/edit_api_key', data);
export const deleteApiKey = (data) => postJson('/api/rp/settings/delete_api_key', data);
export const assignApiKey = (data) => postJson('/api/rp/settings/api_key_assign', data);
