import { useState, useMemo, useRef, memo } from 'react';
import { createPortal } from 'react-dom';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import './ChatBubble.css';

// Configure marked
marked.use({ breaks: true, gfm: true });

function processContent(msg) {
  if (!msg) return '';

  // Streaming text
  if (msg.streamText) return msg.streamText;

  // Parts-based
  if (msg.parts) {
    const parts = Array.isArray(msg.parts) ? msg.parts : [msg.parts];
    return parts
      .map(p => {
        if (typeof p === 'string') return p;
        if (typeof p === 'object' && p !== null) {
          if (p.functionCall || p.functionResponse) return '';
          if (p.thought === true) return ''; // Skip thoughts
          return p.text || p.content || '';
        }
        return String(p);
      })
      .filter(Boolean)
      .join('\n\n');
  }
  return '';
}

function extractThoughts(msg) {
  if (msg.thoughts) return msg.thoughts;
  if (msg.parts && Array.isArray(msg.parts)) {
    const thoughts = msg.parts.filter(p => typeof p === 'object' && p?.thought === true);
    if (thoughts.length > 0) return thoughts.map(t => t.text).join('\n\n');
  }
  return '';
}

function enhanceContentWithImages(text, charId, sessionId) {
  if (!text) return text;
  
  const currentCharId = charId || 'YOUR_CHAR_ID'; 
  const currentSessionId = sessionId || 'YOUR_SESSION_ID';
  const getUrl = (filename) => `/assets/Characters/${currentCharId}/Histories/${currentSessionId}/storage/${filename}`;

  // 1. Fix existing markdown images with relative/bare filenames
  // ![alt](draft_1.png) -> ![alt](/assets/.../draft_1.png)
  const mdRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
  let enhanced = text.replace(mdRegex, (match, alt, url) => {
    url = url.trim();
    if (url.startsWith('draft_') || url.startsWith('attachment_')) {
      return `![${alt}](${getUrl(url)})`;
    }
    return match; // keep as is
  });

  // 1.5 Clean wrapper artifacts like `![draft_1.png]` or `[Attached Image: draft...]` first
  // so we don't end up with leftover brackets around the final image.
  const wrapperRegex = /(?:!\[|\[(?:Attached Image:\s*)?)(draft_\d+_image_[a-f0-9]{6}\.(?:png|jpg|jpeg|gif|webp)|attachment_\d+_image_[a-f0-9-]+\.(?:png|jpg|jpeg|gif|webp))\]/gi;
  enhanced = enhanced.replace(wrapperRegex, (match, filename) => {
    return filename; // Strip the wrapper, just leave the raw filename so looseRegex handles it smoothly
  });

  // 2. Wrap loose filenames in markdown images to render them inline
  const looseRegex = /(draft_\d+_image_[a-f0-9]{6}\.(?:png|jpg|jpeg|gif|webp)|attachment_\d+_image_[a-f0-9-]+\.(?:png|jpg|jpeg|gif|webp))/gi;
  
  enhanced = enhanced.replace(looseRegex, (...args) => {
    const match = args[0];
    const offset = args[args.length - 2];
    const fullString = args[args.length - 1];
    // Check if it's already inside a URL or markdown link by looking at preceding characters
    const prevChar = offset > 0 ? fullString[offset - 1] : '';
    // If preceded by a slash (part of URL path) or quotes, ignore
    if (prevChar === '/' || prevChar === '"' || prevChar === "'") {
      return match;
    }
    return `\n![${match}](${getUrl(match)})\n`;
  });

  return enhanced;
}

function extractImages(msg, enhancedTextContent, charId, sessionId) {
  const images = [];
  const seenSrcs = new Set();
  
  const currentCharId = charId || 'YOUR_CHAR_ID'; 
  const currentSessionId = sessionId || 'YOUR_SESSION_ID';

  const inText = (filename) => {
    if (!enhancedTextContent) return false;
    return enhancedTextContent.includes(filename);
  };

  // 1. Handle injected string filenames from RoleplayChat
  if (msg.images && Array.isArray(msg.images)) {
    msg.images.forEach(img => {
      if (typeof img === 'string') {
        if (img.startsWith('draft_') || img.startsWith('attachment_')) {
          const constructedUrl = `/assets/Characters/${currentCharId}/Histories/${currentSessionId}/storage/${img}`;
          // Only add to attachments if it's not already rendered inline in the text
          if (!seenSrcs.has(constructedUrl) && !inText(img)) {
            seenSrcs.add(constructedUrl);
            images.push({ local_url: constructedUrl, mime_type: 'image/jpeg' });
          }
        }
      } else if (typeof img === 'object' && img !== null) {
        images.push(img);
      }
    });
  }
  
  // 2. Structured image data from parts
  if (msg.parts && Array.isArray(msg.parts)) {
    msg.parts.forEach(p => {
      if (typeof p === 'object' && p !== null) {
        if (p.file_data) images.push(p.file_data);
        if (p.inline_data) images.push(p.inline_data);
        
        // Handle exp_v3 format
        if (p.user_attachment) {
          const att = p.user_attachment;
          if (att.display_name) {
            const constructedUrl = `/assets/Characters/${currentCharId}/Histories/${currentSessionId}/storage/${att.display_name}`;
            if (!seenSrcs.has(constructedUrl) && !inText(att.display_name)) {
              seenSrcs.add(constructedUrl);
              const mime = att.inline_data?.mime_type || 'image/jpeg';
              images.push({ local_url: constructedUrl, mime_type: mime });
            }
          } else if (att.inline_data) {
            images.push(att.inline_data);
          }
        }
      }
    });
  }
  
  return images;
}

function renderMarkdown(text) {
  if (!text) return '';
  let clean = text.replace(/</g, '&lt;');
  clean = clean.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n');
  const html = marked.parse(clean);

  const enhanced = html.replace(
    /<pre><code class="language-(\w+)">([\s\S]*?)<\/code><\/pre>/g,
    (_, lang, code) => `
      <div class="code-wrapper">
        <div class="code-header">
          <div class="code-title-group">
            <div class="mac-dots"><span class="mac-dot mac-red"></span><span class="mac-dot mac-yellow"></span><span class="mac-dot mac-green"></span></div>
            <span class="code-lang">${lang}</span>
          </div>
          <button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.code-wrapper').querySelector('code').textContent)">📋 Copy</button>
        </div>
        <pre><code class="language-${lang}">${code}</code></pre>
      </div>
    `
  );

  // Wrap tables
  const withTables = enhanced.replace(
    /<table>([\s\S]*?)<\/table>/g,
    (_, inner) => `
      <div class="table-wrapper">
        <div class="table-header"><span>Table</span><button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.table-wrapper').querySelector('table').textContent)">📋 Copy</button></div>
        <table>${inner}</table>
      </div>
    `
  );

  return DOMPurify.sanitize(withTables, { ADD_ATTR: ['onclick'] });
}

const ChatBubble = ({ message, index, charName, charAvatar, userName, userAvatar, onDelete, isLast, isGeneratingImage, charId, sessionId }) => {
  const [showThinking, setShowThinking] = useState(false);
  const [previewImg, setPreviewImg] = useState(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const isDragging = useRef(false);
  const lastPan = useRef({ x: 0, y: 0 });
  
  const isUser = message.role === 'user';
  const content = useMemo(() => processContent(message), [message]);
  const finalContent = useMemo(() => enhanceContentWithImages(content, charId, sessionId), [content, charId, sessionId]);
  const thoughts = useMemo(() => extractThoughts(message), [message]);
  
  const images = useMemo(() => extractImages(message, finalContent, charId, sessionId), [message, finalContent, charId, sessionId]);
  
  const html = useMemo(() => renderMarkdown(finalContent), [finalContent]);

  const avatar = isUser ? userAvatar : charAvatar;
  const name = isUser ? userName : charName;

  const handleBubbleClick = (e) => {
    if (e.target.tagName === 'IMG' && !e.target.closest('.msg-avatar')) {
      openPreview(e.target.src);
    }
  };

  const openPreview = (src) => {
    setPreviewImg(src);
    setScale(1);
    setPan({ x: 0, y: 0 });
  };

  const closePreview = () => {
    setPreviewImg(null);
    setScale(1);
    setPan({ x: 0, y: 0 });
  };

  const handleDownload = (e, src) => {
    e.stopPropagation();
    const link = document.createElement('a');
    link.href = src;
    link.download = 'downloaded_image';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleWheel = (e) => {
    e.preventDefault();
    setScale(s => {
      const newScale = s - e.deltaY * 0.005;
      return Math.min(Math.max(0.5, newScale), 5); 
    });
  };

  const handlePointerDown = (e) => {
    isDragging.current = true;
    lastPan.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handlePointerMove = (e) => {
    if (!isDragging.current) return;
    setPan({
      x: e.clientX - lastPan.current.x,
      y: e.clientY - lastPan.current.y
    });
  };

  const handlePointerUp = () => {
    isDragging.current = false;
  };

  return (
    <div className={`msg-row ${isUser ? 'user' : 'character'} animate-slide-up`}>
      <div className="msg-content">
        {/* Header */}
        <div className="msg-header">
          {avatar ? (
            <img src={avatar} alt="" className="msg-avatar" />
          ) : (
            <div className="msg-avatar-placeholder">{name[0]?.toUpperCase()}</div>
          )}
          <span className="msg-name">{name}</span>
        </div>

        {/* Thinking */}
        {thoughts && (
          <details className="thinking-box" open={showThinking}>
            <summary onClick={(e) => { e.preventDefault(); setShowThinking(!showThinking); }}>
              💭 Thinking Process
            </summary>
            {showThinking && <div className="thought-content">{thoughts}</div>}
          </details>
        )}

        {/* Loading Indicator */}
        {isGeneratingImage && (
          <div className="image-loader">
            <span className="loader-text">✨ Generating image...</span>
            <div className="spinner"></div>
          </div>
        )}

        {/* Bubble */}
        <div className="msg-bubble" onClick={handleBubbleClick}>
          <div dangerouslySetInnerHTML={{ __html: html }} />
          {message.isStreaming && <span className="typing-cursor">▋</span>}
        </div>

        {/* Images */}
        {images.map((img, i) => {
          const src = img.local_url || img.local_path || img.url || img.path ||
            (img.data ? `data:${img.mime_type || 'image/png'};base64,${img.data}` : img.file_uri) || '';
          return src ? (
            <img
              key={i}
              src={src}
              className="chat-image"
              alt="Attachment"
              onClick={() => openPreview(src)}
            />
          ) : null;
        })}

        {/* Toolbar */}
        {index >= 0 && !message.isStreaming && (
          <div className="msg-toolbar">
            <button className="tool-btn" onClick={() => navigator.clipboard.writeText(content)} title="Copy">
              📋
            </button>
            <button className="tool-btn delete" onClick={() => onDelete(index)} title="Delete">
              🗑
            </button>
          </div>
        )}
      </div>

      {previewImg && createPortal(
        <div 
          className="img-preview-overlay" 
          onClick={closePreview}
          onWheel={handleWheel}
        >
          <div 
            className="img-preview-container" 
            onClick={e => e.stopPropagation()}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerUp}
          >
            <img 
              src={previewImg} 
              alt="Preview" 
              className="img-preview-full" 
              style={{
                transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
                transition: isDragging.current ? 'none' : 'transform 0.1s ease',
                cursor: isDragging.current ? 'grabbing' : 'grab'
              }}
              draggable="false"
            />
            <div className="img-preview-actions">
              <button className="preview-action-btn" onClick={(e) => handleDownload(e, previewImg)}>💾 Save Image</button>
              <button className="preview-action-btn" onClick={() => { setScale(1); setPan({x:0, y:0}); }}>⟲ Reset Zoom</button>
              <button className="preview-action-btn close" onClick={closePreview}>✕ Close</button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

export default memo(ChatBubble, (prev, next) => {
  if (prev.isLast !== next.isLast) return false;
  if (prev.isGeneratingImage !== next.isGeneratingImage) return false;
  if (prev.index !== next.index) return false;
  
  if (prev.charId !== next.charId) return false;
  if (prev.sessionId !== next.sessionId) return false;
  
  const pMsg = prev.message;
  const nMsg = next.message;
  
  if (pMsg.role !== nMsg.role) return false;
  if (pMsg.timestamp !== nMsg.timestamp) return false;
  if (pMsg.streamText !== nMsg.streamText) return false;
  if (pMsg.isStreaming !== nMsg.isStreaming) return false;
  if (pMsg.thoughts !== nMsg.thoughts) return false;
  if (pMsg.isGroupedTool !== nMsg.isGroupedTool) return false;
  if (pMsg.originalIndex !== nMsg.originalIndex) return false;

  const pParts = Array.isArray(pMsg.parts) ? pMsg.parts : [pMsg.parts];
  const nParts = Array.isArray(nMsg.parts) ? nMsg.parts : [nMsg.parts];
  if (pParts.length !== nParts.length) return false;

  const pImgs = pMsg.images || [];
  const nImgs = nMsg.images || [];
  if (pImgs.length !== nImgs.length) return false;
  
  return true;
});