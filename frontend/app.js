const state = { style: "concise", thinking: "medium", history: JSON.parse(localStorage.getItem("atlasiq-history") || "[]"), busy: false, crawlRunning: false, sourceUrl: "https://jssstuniv.in/", requestId: null, abortController: null };
const elements = {
  chat: document.querySelector("#chat"), form: document.querySelector("#chat-form"), input: document.querySelector("#question-input"),
  send: document.querySelector("#send-button"), sendIcon: document.querySelector("#send-icon"), stopIcon: document.querySelector("#stop-icon"), clear: document.querySelector("#clear-button"), report: document.querySelector("#report-button"), refresh: document.querySelector("#refresh-button"), store: document.querySelector("#store-button"),
  progress: document.querySelector("#crawl-progress"), progressBar: document.querySelector("#progress-bar"), crawlLabel: document.querySelector("#crawl-label"),
  crawlPercent: document.querySelector("#crawl-percent"), statusDot: document.querySelector("#status-dot"), modelStatus: document.querySelector("#model-status"),
  modelName: document.querySelector("#model-name"), knowledgeCount: document.querySelector("#knowledge-count"), seedCount: document.querySelector("#seed-count"),
  webCount: document.querySelector("#web-count"), previewCount: document.querySelector("#preview-count"), lastRefresh: document.querySelector("#last-refresh"), toast: document.querySelector("#toast"),
  sourceUrl: document.querySelector("#source-url"), sidebar: document.querySelector(".sidebar"), menu: document.querySelector("#menu-button")
};

function escapeText(value) { const node = document.createElement("span"); node.textContent = value; return node.innerHTML; }
function showToast(message) { elements.toast.textContent = message; elements.toast.classList.add("show"); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => elements.toast.classList.remove("show"), 3500); }
function formatDate(value) { if (!value) return "Never"; return new Intl.DateTimeFormat(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}).format(new Date(value)); }
function scrollToChat() { requestAnimationFrame(() => window.scrollTo({top:document.body.scrollHeight,behavior:"smooth"})); }
function displayText(value) { return value.replace(/\*\*(.*?)\*\*/g,"$1").replace(/^#{1,6}\s+/gm,"").replace(/^\s*\*\s/gm,"• "); }
function setGenerating(active) { elements.sendIcon.classList.toggle("hidden",active); elements.stopIcon.classList.toggle("hidden",!active); elements.send.setAttribute("aria-label",active ? "Stop response" : "Send question"); }
function selectedSourceUrl() {
  const parsed = new URL(elements.sourceUrl.value.trim());
  if (!['http:','https:'].includes(parsed.protocol)) throw new Error("Enter a complete http:// or https:// website URL.");
  parsed.hash = "";
  return parsed.toString();
}

function addMessage(role, text = "") {
  const wrapper = document.createElement("div"); wrapper.className = `message ${role}`;
  const avatar = document.createElement("div"); avatar.className = `avatar ${role === "assistant" ? "assistant-avatar" : "user-avatar"}`; avatar.textContent = role === "assistant" ? "W" : "You";
  const body = document.createElement("div"); body.className = "message-body";
  const paragraph = document.createElement("p"); paragraph.textContent = text; body.append(paragraph);
  const copy = document.createElement("button"); copy.className="copy-message"; copy.textContent="Copy"; copy.addEventListener("click",()=>navigator.clipboard.writeText(paragraph.textContent)); body.append(copy); wrapper.append(avatar, body); elements.chat.append(wrapper); scrollToChat();
  return { wrapper, body, paragraph };
}

function renderSources(body, sources) {
  if (!sources?.length) return;
  const container = document.createElement("div"); container.className = "sources";
  sources.forEach(source => {
    const link = document.createElement("a"); link.className = "source-link"; link.textContent = `[${source.index}] ${source.title}`;
    if (/^https?:\/\//.test(source.url)) { link.href = source.url; link.target = "_blank"; link.rel = "noopener noreferrer"; }
    container.append(link);
  });
  body.append(container);
}

function renderChart(body, chart) {
  if (!chart?.labels?.length || chart.labels.length !== chart.values?.length) return;
  const card = document.createElement("div"); card.className = "chart-card";
  const title = document.createElement("h3"); title.textContent = chart.title || "Data analysis";
  const canvas = document.createElement("canvas"); canvas.setAttribute("role","img"); canvas.setAttribute("aria-label",title.textContent);
  card.append(title,canvas); body.append(card);
  const width = Math.max(360,Math.min(720,body.clientWidth - 30)), height = 260, ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio; canvas.height = height * ratio; canvas.style.height = `${height}px`;
  const context = canvas.getContext("2d"); context.scale(ratio,ratio); context.font = "11px system-ui"; context.textAlign = "center";
  const padding = {top:18,right:18,bottom:58,left:48}, plotWidth = width-padding.left-padding.right, plotHeight = height-padding.top-padding.bottom;
  const values = chart.values.map(Number), minimum = Math.min(0,...values), maximum = Math.max(...values), span = maximum-minimum || 1;
  context.strokeStyle = "#394052"; context.fillStyle = "#8e96a8"; context.lineWidth = 1;
  context.beginPath(); context.moveTo(padding.left,padding.top); context.lineTo(padding.left,height-padding.bottom); context.lineTo(width-padding.right,height-padding.bottom); context.stroke();
  const x = index => padding.left + plotWidth*(index+.5)/values.length, y = value => padding.top + plotHeight*(maximum-value)/span;
  if (chart.type === "line") {
    context.strokeStyle = "#c8b6ff"; context.lineWidth = 2; context.beginPath(); values.forEach((value,index) => index ? context.lineTo(x(index),y(value)) : context.moveTo(x(index),y(value))); context.stroke();
    values.forEach((value,index) => { context.fillStyle="#9bd8f5"; context.beginPath(); context.arc(x(index),y(value),4,0,Math.PI*2); context.fill(); });
  } else {
    const barWidth = Math.max(8,plotWidth/values.length*.62); values.forEach((value,index) => { const top=y(Math.max(value,0)), bottom=y(Math.min(value,0)); context.fillStyle="#c8b6ff"; context.fillRect(x(index)-barWidth/2,top,barWidth,Math.max(2,bottom-top)); });
  }
  values.forEach((value,index) => { context.fillStyle="#dfe4ef"; context.fillText(String(value),x(index),Math.max(12,y(value)-7)); context.fillStyle="#8e96a8"; const label=String(chart.labels[index]); context.fillText(label.length>12 ? `${label.slice(0,11)}…` : label,x(index),height-padding.bottom+18); });
  if (chart.y_label) { context.save(); context.translate(13,height/2); context.rotate(-Math.PI/2); context.fillText(chart.y_label,0,0); context.restore(); }
  if (chart.x_label) context.fillText(chart.x_label,padding.left+plotWidth/2,height-8);
}

async function ask(question) {
  const clean = question.trim(); if (!clean || state.busy) return;
  try { state.sourceUrl = selectedSourceUrl(); } catch (error) { showToast(error.message); elements.sourceUrl.focus(); return; }
  const requestId = crypto.randomUUID(); state.requestId = requestId; state.abortController = new AbortController(); state.busy = true; setGenerating(true); elements.input.value = ""; resizeInput();
  addMessage("user", clean); state.history.push({role:"user",content:clean,thinking:state.thinking});
  const assistant = addMessage("assistant"); assistant.paragraph.classList.add("typing");
  let answer = "", sources = [];
  try {
    const response = await fetch("/api/chat", {method:"POST",headers:{"Content-Type":"application/json"},signal:state.abortController.signal,body:JSON.stringify({question:clean,style:state.style,thinking_level:state.thinking,history:state.history.slice(-12),site_url:state.sourceUrl,request_id:requestId})});
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = "";
    while (true) {
      const {value,done} = await reader.read(); buffer += decoder.decode(value || new Uint8Array(),{stream:!done});
      const lines = buffer.split("\n"); buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue; const event = JSON.parse(line);
        if (event.type === "sources") { sources = event.sources; const badge=document.createElement("span"); badge.className="thinking-badge"; badge.textContent=`${event.thinking_level} thinking`; assistant.body.prepend(badge); }
        if (event.type === "token") { answer += event.content; assistant.paragraph.textContent = displayText(answer); scrollToChat(); }
        if (event.type === "chart") renderChart(assistant.body,event.chart);
      }
      if (done) break;
    }
    assistant.paragraph.classList.remove("typing"); renderSources(assistant.body,sources);
    state.history.push({role:"assistant",content:answer,thinking:state.thinking}); state.history = state.history.slice(-24); localStorage.setItem("atlasiq-history",JSON.stringify(state.history));
  } catch (error) {
    assistant.paragraph.classList.remove("typing");
    if (error.name === "AbortError") { assistant.paragraph.textContent = displayText(answer || "Response stopped."); if (answer) state.history.push({role:"assistant",content:answer}); }
    else assistant.paragraph.textContent = `I couldn't complete that request. ${error.message}`;
  } finally { if (state.requestId === requestId) { state.busy = false; state.requestId = null; state.abortController = null; setGenerating(false); elements.input.focus(); } }
}

function stopGeneration() {
  if (!state.busy || !state.requestId) return;
  const requestId = state.requestId;
  fetch(`/api/chat/${encodeURIComponent(requestId)}/stop`,{method:"POST",keepalive:true}).catch(()=>{});
  state.abortController?.abort();
}

async function updateStatus() {
  try {
    const sourceUrl = selectedSourceUrl(); state.sourceUrl = sourceUrl;
    const response = await fetch(`/api/status?site_url=${encodeURIComponent(sourceUrl)}`,{cache:"no-store"}); if (!response.ok) throw new Error(); const data = await response.json();
    elements.statusDot.classList.toggle("ready",data.model.ready); elements.modelStatus.textContent = data.model.ready ? "Model ready" : "Ollama unavailable"; elements.modelName.textContent = data.model.model;
    const previewChunks = data.knowledge.preview_chunks || 0; elements.knowledgeCount.textContent = previewChunks ? `${previewChunks} preview` : `${data.knowledge.total_documents} stored`; elements.seedCount.textContent = data.knowledge.seed_documents; elements.webCount.textContent = data.knowledge.web_chunks; elements.previewCount.textContent = previewChunks; elements.lastRefresh.textContent = formatDate(data.knowledge.last_refresh);
    state.crawlRunning = data.crawl.running || data.crawl.storing; elements.refresh.disabled = state.crawlRunning; elements.sourceUrl.disabled = state.crawlRunning; elements.progress.classList.toggle("hidden",!state.crawlRunning);
    const result = data.crawl.last_result, sameSite = result && new URL(result.url).hostname.replace(/^www\./,"") === new URL(sourceUrl).hostname.replace(/^www\./,""); elements.store.classList.toggle("hidden",!sameSite || result.stored || data.crawl.running); elements.store.disabled = data.crawl.storing;
    if (state.crawlRunning) { const total = data.crawl.total_pages || 12, percent = data.crawl.storing ? 100 : Math.min(100,Math.round((data.crawl.completed_pages/total)*100)); elements.progressBar.style.width = `${percent}%`; elements.crawlPercent.textContent = `${percent}%`; elements.crawlLabel.textContent = data.crawl.storing ? "Storing in MySQL…" : data.crawl.current_url || "Starting crawler…"; }
    if (data.crawl.error && data.crawl.error !== updateStatus.lastError) { updateStatus.lastError = data.crawl.error; showToast(data.crawl.error); }
    if (result && JSON.stringify(result) !== updateStatus.lastResult) { updateStatus.lastResult = JSON.stringify(result); showToast(result.stored ? `Stored ${result.chunks} chunks in MySQL.` : `Gathered ${result.chunks} chunks. You can ask now, or store them for later.`); }
  } catch { elements.modelStatus.textContent = "Backend unavailable"; elements.statusDot.classList.remove("ready"); }
  clearTimeout(updateStatus.timer); updateStatus.timer = setTimeout(updateStatus,state.crawlRunning ? 1200 : 7000);
}

async function refreshKnowledge() {
  if (state.crawlRunning) return; elements.refresh.disabled = true;
  try { state.sourceUrl = selectedSourceUrl(); const response = await fetch("/api/knowledge/refresh",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:state.sourceUrl})}); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Crawl failed"); showToast("Website crawl started in the background."); updateStatus(); }
  catch (error) { showToast(error.message); elements.refresh.disabled = false; }
}

async function storeKnowledge() {
  elements.store.disabled = true;
  try { const response = await fetch("/api/knowledge/store",{method:"POST"}); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Store failed"); showToast(data.message); updateStatus(); }
  catch (error) { showToast(error.message); elements.store.disabled = false; }
}

function resizeInput() { elements.input.style.height = "auto"; elements.input.style.height = `${Math.min(elements.input.scrollHeight,130)}px`; }
elements.form.addEventListener("submit",event => { event.preventDefault(); state.busy ? stopGeneration() : ask(elements.input.value); });
elements.input.addEventListener("input",resizeInput);
elements.input.addEventListener("keydown",event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); elements.form.requestSubmit(); } });
elements.clear.addEventListener("click",() => { state.history = []; localStorage.removeItem("atlasiq-history"); elements.chat.innerHTML = ""; addMessage("assistant","Conversation cleared. What would you like to know about the selected website?"); });
elements.report.addEventListener("click",()=>{ const report=`# AtlasIQ Research Report\n\nSource: ${elements.sourceUrl.value}\nGenerated: ${new Date().toLocaleString()}\n\n${state.history.map(item=>`## ${item.role==='user'?'Question':`Answer (${item.thinking || 'unknown'} thinking)`}\n\n${item.content}`).join('\n\n')}`; const link=document.createElement('a'); link.href=URL.createObjectURL(new Blob([report],{type:'text/markdown'})); link.download='atlasiq-report.md'; link.click(); URL.revokeObjectURL(link.href); });
elements.refresh.addEventListener("click",refreshKnowledge);
elements.store.addEventListener("click",storeKnowledge);
elements.sourceUrl.addEventListener("change",() => { state.history = []; updateStatus(); });
elements.menu.addEventListener("click",() => elements.sidebar.classList.toggle("open"));
document.querySelectorAll(".style-button").forEach(button => button.addEventListener("click",() => { document.querySelectorAll(".style-button").forEach(item => item.classList.remove("active")); button.classList.add("active"); state.thinking = button.dataset.thinking; }));
document.querySelectorAll(".quick-card").forEach(button => button.addEventListener("click",() => ask(button.dataset.question)));
if(state.history.length){elements.chat.innerHTML="";state.history.forEach(item=>addMessage(item.role,item.content));} updateStatus(); elements.input.focus();
