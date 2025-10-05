const socket = io();

function initChat(orderId){
  socket.emit("join", { order_id: orderId });

  socket.on("system", d => {
    appendChatLine("system", d.msg);
  });

  socket.on("new_message", d => {
    appendChatLine(d.sender, d.content);
  });

  socket.on("error", d => {
    console.error("socket error", d);
  });

  document.getElementById("sendBtn")?.addEventListener("click", () => {
    const el = document.getElementById("msg");
    const content = el.value.trim();
    if(!content) return;
    socket.emit("send_message", { order_id: orderId, content });
    el.value = "";
  });
}

function appendChatLine(sender, text){
  const chat = document.getElementById("chat");
  if(!chat) return;
  const wrapper = document.createElement("div");
  wrapper.className = "mb-2";
  const time = new Date().toLocaleString();
  wrapper.innerHTML = `<div class="text-xs text-gray-400">${time} • ${sender}</div><div>${text}</div>`;
  chat.appendChild(wrapper);
  chat.scrollTop = chat.scrollHeight;
}
