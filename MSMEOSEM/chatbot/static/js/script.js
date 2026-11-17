// ====================== script.js ======================

// 🔹 BASIC DOM ELEMENTS
const chatbotBtn = document.getElementById('chatbotBtn');
const openChatbotBtn = document.getElementById('openChatbotBtn');
const closeChatbotBtn = document.getElementById('closeChatbotBtn');
const chatbotModal = document.getElementById('chatbotModal');
const appHeader = document.getElementById('appHeader');
const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const stopBtn = document.getElementById('stopBtn');
const clearChatBtn = document.getElementById('clearChatBtn');
const aboutBtn = document.getElementById('aboutBtn');
const helpBtn = document.getElementById('helpBtn');
const scrollToTopBtn = document.getElementById('scrollToTopBtn');
const scrollToBottomBtn = document.getElementById('scrollToBottomBtn');

// NEW UI GROUPS (these should exist in your HTML where we updated earlier)
const mainOptions = document.getElementById("main-options");      // main four buttons container
const upiconOptions = document.getElementById("upicon-options");  // UPICON suboptions container
const osemOptions = document.getElementById("osem-options");      // OSEM suboptions container

// STATE
let chatHistory = [];
let typingIndicator = null;
let controller = null;
let isGenerating = false;

// INIT
document.addEventListener("DOMContentLoaded", init);

function init() {
  setupEventListeners();
  // Ensure submenus hidden initially
  if (upiconOptions) upiconOptions.style.display = "none";
  if (osemOptions) osemOptions.style.display = "none";
  scrollToBottom();
}

// SETUP EVENTS
function setupEventListeners() {
  // Chat open/close toggles
  if (chatbotBtn) chatbotBtn.addEventListener('click', toggleChatbot);
  if (openChatbotBtn) openChatbotBtn.addEventListener('click', toggleChatbot);
  if (closeChatbotBtn) closeChatbotBtn.addEventListener('click', toggleChatbot);

  // Send & input handling
  if (sendBtn) sendBtn.addEventListener('click', sendMessage);
  if (userInput) {
    userInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendMessage();
    });
  }

  // Stop & clear
  if (stopBtn) stopBtn.addEventListener('click', stopGeneration);
  if (clearChatBtn) clearChatBtn.addEventListener('click', clearChatHistory);

  // About & Help quick shortcuts
  if (aboutBtn) {
    aboutBtn.addEventListener('click', () => {
      toggleChatbot();
      setTimeout(() => {
        if (userInput) userInput.value = "Tell me about MSME OSEM";
        sendMessage();
      }, 300);
    });
  }
  if (helpBtn) {
    helpBtn.addEventListener('click', () => {
      toggleChatbot();
      setTimeout(() => {
        if (userInput) userInput.value = "How can you help me with my business?";
        sendMessage();
      }, 300);
    });
  }

  // Global click listener for quick-reply buttons
  document.addEventListener("click", handleQuickReplyClick);

  // Scroll buttons
  if (scrollToTopBtn) scrollToTopBtn.addEventListener('click', () => { chatMessages.scrollTop = 0; });
  if (scrollToBottomBtn) scrollToBottomBtn.addEventListener('click', scrollToBottom);

  // chatMessages scroll watcher (keeps buttons visible in this layout)
  if (chatMessages) {
    chatMessages.addEventListener('scroll', () => {
      // Simple behavior: keep buttons available (you can customize visibility logic)
      if (scrollToTopBtn) scrollToTopBtn.style.display = 'flex';
      if (scrollToBottomBtn) scrollToBottomBtn.style.display = 'flex';
    });
  }
}

// HANDLE QUICK REPLY BUTTONS (main logic for main menu and submenus)
function handleQuickReplyClick(e) {
  const btn = e.target;
  if (!btn.classList.contains("quick-reply-btn")) return;

  const replyText = btn.getAttribute("data-reply") || btn.textContent.trim();

  // Prevent sending messages for Expert / Business flows
  if (btn.classList.contains("district-option")) return;
  if (btn.id === "byDistrictBtn" || btn.id === "byDesignationBtn") return;

  // MAIN MENU: UPICON
  if (btn.dataset.main === "upicon") {
    upiconOptions.style.display = "block";
    osemOptions.style.display = "none";
    return;
  }

  // MAIN MENU: OSEM
  if (btn.dataset.main === "osem") {
    osemOptions.style.display = "block";
    upiconOptions.style.display = "none";
    return;
  }

  // FIND EXPERTS
  if (btn.id === "expert-list-btn") {
    showExpertOptions();
    return;
  }

  // FIND BUSINESSES
  if (btn.id === "business-list-btn") {
    showBusinessDistrictSelection();
    return;
  }

  // LOAN
  if (replyText === "Check for CM Yuva Loan" || btn.id === "checkLoanBtn") {
    startLoanEligibilityCheck();
    return;
  }

  // LOAN AGE/CERT selection
  if (btn.classList.contains("loan-age-btn")) {
    handleLoanAgeSelection(btn.dataset.age);
    return;
  }
  if (btn.classList.contains("loan-cert-btn")) {
    handleLoanCertSelection(btn.dataset.cert);
    return;
  }

  // NORMAL BUTTON → send to backend
  if (replyText) {
    userInput.value = replyText;
    sendMessage();
  }
}


// TOGGLE CHATBOT VISIBILITY
function toggleChatbot() {
  if (!chatbotModal) return;
  chatbotModal.classList.toggle("active");
  if (appHeader) appHeader.classList.toggle("hidden");
  if (chatbotBtn) chatbotBtn.classList.toggle("hidden");

  if (chatbotModal.classList.contains("active") && userInput) {
    userInput.focus();
  }
}

// DISPLAY MESSAGE (user or bot)
function displayMessage(sender, content) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `message message-${sender}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = sender === 'user' ? 'Y' : 'O';

  const messageContent = document.createElement("div");
  messageContent.className = "message-content";
  messageContent.innerHTML = content;

  messageDiv.appendChild(avatar);
  messageDiv.appendChild(messageContent);

  chatMessages.appendChild(messageDiv);
  scrollToBottom();

  chatHistory.push({
    sender,
    content,
    timestamp: new Date().toISOString()
  });
}

// TYPING INDICATOR
function showTypingIndicator() {
  if (!typingIndicator) {
    typingIndicator = document.createElement('div');
    typingIndicator.className = 'typing-indicator';
    typingIndicator.innerHTML = '<span></span><span></span><span></span>';
    chatMessages.appendChild(typingIndicator);
    scrollToBottom();
  }
}
function removeTypingIndicator() {
  if (typingIndicator) {
    typingIndicator.remove();
    typingIndicator = null;
  }
}

// SCROLL TO BOTTOM
function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
  if (scrollToBottomBtn) {
    scrollToBottomBtn.classList.add('active');
    setTimeout(() => scrollToBottomBtn.classList.remove('active'), 300);
  }
}

// SEND MESSAGE (calls backend /chat endpoint and streams response)
async function sendMessage() {
  if (!userInput) return;
  const message = userInput.value.trim();
  if (!message) return;

  // Show user message
  displayMessage('user', message);
  userInput.value = '';

  // Disable input & show typing indicator
  disableInput();
  showTypingIndicator();

  // Show stop button, hide send
  if (stopBtn) stopBtn.style.display = 'flex';
  if (sendBtn) sendBtn.style.display = 'none';

  controller = new AbortController();
  isGenerating = true;

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    await processStreamedResponse(response);

  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('Request aborted');
      displayMessage('bot', 'Response generation stopped.');
    } else {
      console.error(error);
      displayMessage('bot', 'Sorry, something went wrong. Please try again later.');
    }
  } finally {
    isGenerating = false;
    if (stopBtn) stopBtn.style.display = 'none';
    if (sendBtn) sendBtn.style.display = 'flex';
    enableInput();
    removeTypingIndicator();
    if (userInput) userInput.focus();
  }
}

function disableInput() {
  if (userInput) userInput.disabled = true;
  if (sendBtn) sendBtn.disabled = true;
}
function enableInput() {
  if (userInput) userInput.disabled = false;
  if (sendBtn) sendBtn.disabled = false;
}

// PROCESS STREAMED RESPONSE FROM BACKEND
async function processStreamedResponse(response) {
  removeTypingIndicator();

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let botMessage = '';

  // Create container for bot response
  const messageDiv = document.createElement('div');
  messageDiv.className = 'message message-bot';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = 'O';

  const messageContent = document.createElement('div');
  messageContent.className = 'message-content';

  messageDiv.appendChild(avatar);
  messageDiv.appendChild(messageContent);
  chatMessages.appendChild(messageDiv);
  scrollToBottom();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    botMessage += decoder.decode(value, { stream: true });
    messageContent.innerHTML = botMessage;
    scrollToBottom();
  }
}

// STOP GENERATION
function stopGeneration() {
  if (controller) controller.abort();
  isGenerating = false;
  removeTypingIndicator();
  if (stopBtn) stopBtn.style.display = 'none';
  if (sendBtn) sendBtn.style.display = 'flex';
}

// CLEAR CHAT HISTORY (resets to initial welcome with main options)
async function clearChatHistory() {
  const confirmed = confirm('Are you sure you want to clear the chat history?');
  if (!confirmed) return;

  // Optional: call backend to clear server session
  try {
    await fetch('/api/clear_chat', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
  } catch (err) {
    // ignore failure — we'll reset UI anyway
    console.warn('clear_chat API failed or not present', err);
  }

  chatMessages.innerHTML = `
    <div class="message message-bot">
      <div class="message-avatar">O</div>
      <div class="message-content">
        <p>Hello! I'm your MSME OSEM Assistant. How can I help you today?</p>
        <div class="quick-replies" id="main-options">
          <button class="quick-reply-btn" data-main="upicon">UPICON</button>
          <button class="quick-reply-btn" data-main="osem">OSEM</button>
          <button class="quick-reply-btn" id="expert-list-btn">Find Experts</button>
          <button class="quick-reply-btn" id="business-list-btn">Find Businesses</button>
        </div>
      </div>
    </div>
  `;
  // Re-bind submenu references (since we replaced innerHTML)
  // If your upiconOptions / osemOptions are separate elements outside of chatMessages, these lines are not necessary.
  if (upiconOptions) upiconOptions.style.display = 'none';
  if (osemOptions) osemOptions.style.display = 'none';
  chatHistory = [];
}

// ========================= Expert / Business / Loan flows =========================

// SHOW EXPERT OPTIONS (By District or By Expertise)
function showExpertOptions() {
  const messageDiv = document.createElement('div');
  messageDiv.className = 'message message-bot';
  messageDiv.innerHTML = `
    <div class="message-avatar">O</div>
    <div class="message-content">
      <p>How would you like to find experts?</p>
      <div class="expert-options" style="display:flex; gap:12px; margin-top:12px; flex-wrap:wrap;">
        <button id="byDistrictBtn" class="quick-reply-btn">By District</button>
        <button id="byDesignationBtn" class="quick-reply-btn">By Expertise</button>
      </div>
    </div>
  `;
  chatMessages.appendChild(messageDiv);
  scrollToBottom();

  // Add listeners
  document.getElementById('byDistrictBtn').addEventListener('click', showDistrictSelection);
  document.getElementById('byDesignationBtn').addEventListener('click', showDesignationSelection);
}

// SHOW DISTRICT SELECTION (for experts)
function showDistrictSelection() {
  const loadingIndicator = document.createElement('div');
  loadingIndicator.className = 'message message-bot';
  loadingIndicator.innerHTML = `
    <div class="message-avatar">O</div>
    <div class="message-content">Fetching districts...</div>
  `;
  chatMessages.appendChild(loadingIndicator);
  scrollToBottom();

  fetch('/api/expert_list')
    .then(res => res.json())
    .then(data => {
      // remove loading
      loadingIndicator.remove();

      if (data.districts && data.districts.length) {
        const districtButtons = data.districts.map(d => `<button class="district-option quick-reply-btn" data-district="${d}">${d}</button>`).join('');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message message-bot';
        messageDiv.innerHTML = `
          <div class="message-avatar">O</div>
          <div class="message-content">
            <p>Please select a district:</p>
            <div class="district-options" style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">${districtButtons}</div>
          </div>
        `;
        chatMessages.appendChild(messageDiv);
        scrollToBottom();

        // Add listeners to new district-option buttons
        document.querySelectorAll('.district-option').forEach(btn => {
          btn.addEventListener('click', () => {
            const district = btn.getAttribute('data-district');
            fetchExpertsForDistrict(district);
          });
        });

      } else {
        displayMessage('bot', 'No districts with experts found.');
      }
    })
    .catch(err => {
      console.error('Error fetching districts', err);
      loadingIndicator.remove();
      displayMessage('bot', 'Sorry, I could not fetch districts right now.');
    });
}

// FETCH EXPERTS FOR DISTRICT
function fetchExpertsForDistrict(district) {
  const loading = document.createElement('div');
  loading.className = 'message message-bot';
  loading.innerHTML = `<div class="message-avatar">O</div><div class="message-content">Finding experts in ${district}...</div>`;
  chatMessages.appendChild(loading);
  scrollToBottom();

  fetch(`/api/experts_in_district?district=${encodeURIComponent(district)}`)
    .then(res => res.json())
    .then(data => {
      loading.remove();
      if (data.experts && data.experts.length) {
        const expertsList = data.experts.map(ex => `
          <div class="expert-card" style="border:1px solid #eee;padding:8px;border-radius:8px;margin-bottom:8px;">
            <strong>${ex.name}</strong>
            <div>Designation: ${ex.designation || 'N/A'}</div>
            <div>Email: ${ex.email || 'N/A'}</div>
            <div>Phone: ${ex.mobile || 'N/A'}</div>
          </div>
        `).join('');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message message-bot';
        messageDiv.innerHTML = `
          <div class="message-avatar">O</div>
          <div class="message-content">
            <p>Experts in ${district}:</p>
            <div class="experts-list" style="margin-top:8px">${expertsList}</div>
          </div>
        `;
        chatMessages.appendChild(messageDiv);
        scrollToBottom();
      } else {
        displayMessage('bot', `No experts found in ${district}.`);
      }
    })
    .catch(err => {
      console.error('Error fetching experts', err);
      loading.remove();
      displayMessage('bot', 'Sorry, I couldn\'t fetch the experts. Please try again later.');
    });
}

// SHOW DESIGNATION (expertise) SELECTION
function showDesignationSelection() {
  const loading = document.createElement('div');
  loading.className = 'message message-bot';
  loading.innerHTML = `<div class="message-avatar">O</div><div class="message-content">Fetching expertise areas...</div>`;
  chatMessages.appendChild(loading);
  scrollToBottom();

  fetch('/api/expert_designations')
    .then(res => res.json())
    .then(data => {
      loading.remove();
      if (data.designations && data.designations.length) {
        const desButtons = data.designations.map(d => `<button class="district-option quick-reply-btn" data-designation="${d}">${d}</button>`).join('');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message message-bot';
        messageDiv.innerHTML = `
          <div class="message-avatar">O</div>
          <div class="message-content">
            <p>Please select an expertise area:</p>
            <div class="district-options" style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">${desButtons}</div>
          </div>
        `;
        chatMessages.appendChild(messageDiv);
        scrollToBottom();

        document.querySelectorAll('.district-option').forEach(btn => {
          btn.addEventListener('click', () => {
            const designation = btn.getAttribute('data-designation');
            fetchExpertsByDesignation(designation);
          });
        });
      } else {
        displayMessage('bot', 'No expertise areas found.');
      }
    })
    .catch(err => {
      loading.remove();
      console.error('Error fetching designations', err);
      displayMessage('bot', 'Sorry, I couldn\'t fetch the expertise areas. Please try again later.');
    });
}

// FETCH EXPERTS BY DESIGNATION
function fetchExpertsByDesignation(designation) {
  const loading = document.createElement('div');
  loading.className = 'message message-bot';
  loading.innerHTML = `<div class="message-avatar">O</div><div class="message-content">Finding ${designation} experts...</div>`;
  chatMessages.appendChild(loading);
  scrollToBottom();

  fetch(`/api/experts_by_designation?designation=${encodeURIComponent(designation)}`)
    .then(res => res.json())
    .then(data => {
      loading.remove();
      if (data.experts && data.experts.length) {
        const list = data.experts.map(ex => `
          <div class="expert-card" style="border:1px solid #eee;padding:8px;border-radius:8px;margin-bottom:8px;">
            <strong>${ex.name}</strong>
            <div>Designation: ${designation}</div>
            <div>District: ${ex.district || 'N/A'}</div>
            <div>Email: ${ex.email || 'N/A'}</div>
            <div>Phone: ${ex.mobile || 'N/A'}</div>
          </div>
        `).join('');
        displayMessage('bot', `<p>${designation} experts:</p><div class="experts-list" style="margin-top:8px">${list}</div>`);
      } else {
        displayMessage('bot', `No ${designation} experts found.`);
      }
    })
    .catch(err => {
      loading.remove();
      console.error('Error fetching experts by designation', err);
      displayMessage('bot', 'Sorry, I couldn\'t fetch the experts. Please try again later.');
    });
}

// SHOW BUSINESS DISTRICTS (for finding businesses)
function showBusinessDistrictSelection() {
  const loading = document.createElement('div');
  loading.className = 'message message-bot';
  loading.innerHTML = `<div class="message-avatar">O</div><div class="message-content">Fetching business districts...</div>`;
  chatMessages.appendChild(loading);
  scrollToBottom();

  fetch('/api/business_list')
    .then(res => {
      if (!res.ok) throw new Error('Failed to fetch business districts');
      return res.json();
    })
    .then(data => {
      loading.remove();
      if (data.districts && data.districts.length) {
        const btns = data.districts.map(d => `<button class="district-option quick-reply-btn" data-district="${d}">${d}</button>`).join('');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message message-bot';
        messageDiv.innerHTML = `
          <div class="message-avatar">O</div>
          <div class="message-content">
            <p>Please select a district to find businesses:</p>
            <div class="district-options" style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">${btns}</div>
          </div>
        `;
        chatMessages.appendChild(messageDiv);
        scrollToBottom();

        document.querySelectorAll('.district-option').forEach(btn => {
          btn.addEventListener('click', () => {
            const district = btn.getAttribute('data-district');
            fetchBusinessesByDistrict(district);
          });
        });
      } else {
        displayMessage('bot', 'No districts with businesses found.');
      }
    })
    .catch(err => {
      loading.remove();
      console.error('Error fetching business districts', err);
      displayMessage('bot', 'Sorry, I couldn\'t fetch business districts. Please try again later.');
    });
}

// FETCH BUSINESSES BY DISTRICT
function fetchBusinessesByDistrict(district) {
  const loading = document.createElement('div');
  loading.className = 'message message-bot';
  loading.innerHTML = `<div class="message-avatar">O</div><div class="message-content">Loading businesses in ${district}...</div>`;
  chatMessages.appendChild(loading);
  scrollToBottom();

  fetch(`/api/business_in_district?district=${encodeURIComponent(district)}`)
    .then(res => {
      if (!res.ok) throw new Error('Failed to fetch businesses');
      return res.json();
    })
    .then(data => {
      loading.remove();
      const businesses = data.business || [];
      if (businesses.length) {
        const list = businesses.map(b => `
          <div class="business-card" style="border:1px solid #eee;padding:8px;border-radius:8px;margin-bottom:8px;">
            <strong>${b.name}</strong>
            <div>Email: ${b.email || 'N/A'}</div>
            <div>Phone: ${b.mobile || 'N/A'}</div>
            <div>District: ${district}</div>
          </div>
        `).join('');
        displayMessage('bot', `<p>Businesses available in ${district}:</p><div class="businesses-list" style="margin-top:8px">${list}</div>`);
      } else {
        displayMessage('bot', `No businesses found in ${district}.`);
      }
    })
    .catch(err => {
      loading.remove();
      console.error('Error fetching businesses', err);
      displayMessage('bot', 'Sorry, I couldn\'t fetch businesses. Please try again later.');
    });
}

// ========================= Loan eligibility flow =========================

// START LOAN ELIGIBILITY CHECK
function startLoanEligibilityCheck() {
  displayMessage('user', 'I want to check for CM Loan eligibility.');

  const botMessage = document.createElement('div');
  botMessage.className = 'message message-bot';
  botMessage.innerHTML = `
    <div class="message-avatar">O</div>
    <div class="message-content">
      <p>Please select your age range:</p>
      <div class="quick-replies" style="margin-top: 12px;">
        <button class="quick-reply-btn loan-age-btn" data-age="0-20">0-20</button>
        <button class="quick-reply-btn loan-age-btn" data-age="21-40">21-40</button>
      </div>
    </div>
  `;
  chatMessages.appendChild(botMessage);
  scrollToBottom();
}

// HANDLE AGE SELECTION
function handleLoanAgeSelection(age) {
  displayMessage('user', age === '0-20' ? '0-20' : '21-40');

  if (age === '0-20') {
    displayMessage('bot', 'Sorry, minimum age for loan is 21.');
    return;
  }

  // age 21-40 -> ask about certificate
  const botMessage = document.createElement('div');
  botMessage.className = 'message message-bot';
  botMessage.innerHTML = `
    <div class="message-avatar">O</div>
    <div class="message-content">
      <p>Do you have a skill/training certificate?</p>
      <div class="quick-replies" style="margin-top: 12px;">
        <button class="quick-reply-btn loan-cert-btn" data-cert="yes">Yes</button>
        <button class="quick-reply-btn loan-cert-btn" data-cert="no">No</button>
      </div>
    </div>
  `;
  chatMessages.appendChild(botMessage);
  scrollToBottom();
}

// HANDLE CERTIFICATE SELECTION
function handleLoanCertSelection(cert) {
  displayMessage('user', cert === 'yes' ? 'Yes' : 'No');

  if (cert === 'no') {
    displayMessage('bot', 'Sorry, you are not eligible.<br>Visit <a href="https://udyami.upicon.in/" target="_blank">UPICON e-Learnings</a> to take certification.');
  } else {
    displayMessage('bot', 'You are eligible for the loan.<br>Please contact my team for more information and guidance on the next steps.<br>You can reach us via phone, email, or visit our office during working hours.');
  }
}