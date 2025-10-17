/**
 * SCI Sentences Learning Client - JavaScript Functions
 * ملف JavaScript مخصص لتعلم الجمل البسيطة العشرة
 */

class SentencesLearningClient {
  constructor() {
    this.authToken = null;
    this.authEmail = null;
    this.userName = null;
    this.room = null;
    this.audioEl = null;
    // this.sentences = []; // لم تعد هناك حاجة لتخزين الجمل محلياً
    
    // عناصر DOM
    this.elements = {};
    
    // متغيرات المحادثة
    this.currentUserMessage = null;
    this.currentAssistantMessage = null;
    this.lastUserText = '';
    this.lastAssistantText = '';
    this.transcriptionTimeout = null;
    
    this.init();
  }

  async setupLiveKit() {
    try {
      // محاولة تحميل LiveKit من CDN متعدد للتوافق مع جميع المتصفحات
      let LiveKitModule;
      
      try {
        // المحاولة 1: ESM من unpkg
        LiveKitModule = await import('https://unpkg.com/livekit-client@2.15.4/dist/livekit-client.esm.mjs');
      } catch (esmError) {
        console.warn('فشل تحميل ESM، محاولة jsdelivr...', esmError);
        try {
          // المحاولة 2: من jsdelivr كبديل
          LiveKitModule = await import('https://cdn.jsdelivr.net/npm/livekit-client@2.15.4/dist/livekit-client.esm.mjs');
        } catch (jsdelivrError) {
          console.warn('فشل تحميل jsdelivr، محاولة التحميل التقليدي...', jsdelivrError);
          // المحاولة 3: تحميل من window (إذا كان محملاً مسبقاً)
          if (window.LivekitClient) {
            LiveKitModule = window.LivekitClient;
          } else {
            throw new Error('لم يتم العثور على LiveKit. يرجى التأكد من اتصال الإنترنت.');
          }
        }
      }
      
      const { Room, RoomEvent, createLocalAudioTrack, setLogLevel, LogLevel } = LiveKitModule;
      
      if (setLogLevel && LogLevel) {
        setLogLevel(LogLevel.warn);
      }
      
      this.Room = Room;
      this.RoomEvent = RoomEvent;
      this.createLocalAudioTrack = createLocalAudioTrack;
      
      // التحقق من دعم WebRTC
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('المتصفح لا يدعم WebRTC. يرجى استخدام متصفح حديث.');
      }
      
      this.log('تم تحميل LiveKit بنجاح', 'ok');
    } catch (error) {
      this.log('خطأ في تحميل LiveKit: ' + error.message, 'err');
      console.error('LiveKit setup error:', error);
      throw error;
    }
  }

  async init() {
    // تهيئة عناصر DOM
    this.initElements();
    
    // إعداد LiveKit
    await this.setupLiveKit();
    
    // إعداد الصوت
    this.setupAudio();
    
    // استعادة الجلسة
    this.restoreSession();
    
    // تحميل الجمل - تم تعطيله مؤقتاً
    // await this.loadSentences();
    
    // إعداد LiveKit
    await this.setupLiveKit();
    
    // إعداد معالجات الأحداث
    this.setupEventListeners();
    
    // فحص المصادقة
    this.checkAuth();
    
    // عرض معلومات المستخدم
    this.displayUserInfo();
  }

  initElements() {
    const elementIds = [
      'logs', 'joinBtn', 'leaveBtn', 'room', 'name', 'signoutBtn', 'userInfo',
      'chatMessages', 'typingIndicator', 'liveTranscription', 
      'transcriptionText', 'transcriptionIndicator', 'backBtn'
    ];
    
    elementIds.forEach(id => {
      this.elements[id] = document.getElementById(id);
    });
  }

  setupAudio() {
    this.audioEl = document.getElementById('audio');
    if (!this.audioEl) {
      this.audioEl = document.createElement('audio');
      this.audioEl.id = 'audio';
      this.audioEl.autoplay = true;
      this.audioEl.playsInline = true;
      this.audioEl.style.display = 'none';
      document.body.appendChild(this.audioEl);
    } else {
      this.audioEl.autoplay = true;
      this.audioEl.playsInline = true;
    }
  }

  /* تمت إزالة تعريف مكرر لـ setupLiveKit (بنسخة 2.5.7). نستخدم التعريف أعلاه (2.15.4). */


  setupEventListeners() {
    this.elements.joinBtn?.addEventListener('click', () => this.join());
    this.elements.leaveBtn?.addEventListener('click', () => this.leave());
    this.elements.signoutBtn?.addEventListener('click', () => this.doSignout());
    this.elements.backBtn?.addEventListener('click', () => this.goBack());
    
    // التحقق من المصادقة عند تحميل الصفحة
    window.addEventListener('load', () => {
      this.checkAuth();
      this.displayUserInfo();
    });

    // تعبئة حقل الاسم تلقائياً
    if (this.elements.name && localStorage.getItem('user_name')) {
      this.elements.name.value = localStorage.getItem('user_name');
    } else if (this.elements.name) {
      this.elements.name.value = this.randName();
    }
  }

  // === وظائف المصادقة ===
  checkAuth() {
    const token = localStorage.getItem('access_token');
    if (!token) {
      window.location.href = '/login';
      return false;
    }
    return true;
  }

  restoreSession() {
    this.setAuth(
      localStorage.getItem('access_token'), 
      localStorage.getItem('user_email'),
      localStorage.getItem('user_name')
    );
  }

  setAuth(token, email, name) {
    this.authToken = token || null;
    this.authEmail = email || null;
    this.userName = name || null;
    
    if (this.authToken) {
      localStorage.setItem('access_token', this.authToken);
      localStorage.setItem('user_email', this.authEmail || '');
      localStorage.setItem('user_name', this.userName || '');
      
      if (this.elements.userInfo) {
        this.elements.userInfo.textContent = `مرحباً ${this.userName || 'مستخدم'}`;
      }
      
      if (this.elements.name && this.userName) {
        this.elements.name.value = this.userName;
      }
    }
  }

  doSignout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_data');
    window.location.href = '/login';
  }

  displayUserInfo() {
    const userData = localStorage.getItem('user_data');
    const userName = localStorage.getItem('user_name');
    
    let displayName = 'مستخدم';
    
    if (userData) {
      try {
        const user = JSON.parse(userData);
        displayName = user.user_metadata?.full_name || userName || 'مستخدم';
      } catch (e) {
        displayName = userName || 'مستخدم';
      }
    } else if (userName) {
      displayName = userName;
    }
    
    if (this.elements.userInfo) {
      this.elements.userInfo.textContent = `مرحباً ${displayName}`;
    }
  }

  goBack() {
    window.location.href = '/';
  }

  // === وظائف المحادثة ===
  addMessage(content, sender = 'assistant', isTranscription = false, isStreaming = false) {
    if (!this.elements.chatMessages) return null;

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}${isTranscription ? ' transcription' : ''}${isStreaming ? ' streaming' : ''}`;
    
    const headerDiv = document.createElement('div');
    headerDiv.className = 'message-header';
    
    const icon = sender === 'user' ? '👤' : '🤖';
    const name = sender === 'user' ? 'أنت' : 'Friday';
    const time = new Date().toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' });
    
    headerDiv.innerHTML = `<span>${icon} ${name}</span><span>•</span><span>${time}</span>`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;
    
    messageDiv.appendChild(headerDiv);
    messageDiv.appendChild(contentDiv);
    
    this.elements.chatMessages.appendChild(messageDiv);
    this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    
    return messageDiv;
  }

  showTyping(show = true) {
    if (this.elements.typingIndicator) {
      this.elements.typingIndicator.style.display = show ? 'flex' : 'none';
    }
  }

  updateMessage(messageDiv, content, isComplete = false) {
    if (!messageDiv) return;
    
    const contentDiv = messageDiv.querySelector('.message-content');
    if (contentDiv) {
      contentDiv.textContent = content;
      
      if (isComplete) {
        messageDiv.classList.remove('streaming');
      }
    }
    
    this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
  }

  // === وظائف الاتصال ===
  async join() {
    try {
      if (this.elements.joinBtn) this.elements.joinBtn.disabled = true;
      if (this.elements.leaveBtn) this.elements.leaveBtn.disabled = false;

      const identity = this.elements.name?.value.trim() || this.randName();
      const fullName = localStorage.getItem('user_name') || identity;
      const userId = localStorage.getItem('user_data') ? 
        JSON.parse(localStorage.getItem('user_data')).user_id : null;

      // إنشاء غرفة فريدة لكل مستخدم/جلسة لتجنب التداخل
      const timestamp = Date.now();
      const randomId = Math.random().toString(36).substring(2, 9);
      let roomName = `sentences-${userId || randomId}-${timestamp}`;

      if (!this.authToken) {
        throw new Error('يرجى تسجيل الدخول أولاً');
      }

      this.log('بدء جلسة تعلم الجمل البسيطة...');
      this.log(`بيانات المستخدم: ${identity} (${fullName})`);
      
      // إرسال metadata خاص لتعلم الجمل
      const sentencesMetadata = {
        mode: 'sentences_learning',
        total_sentences: 10
      };
      
      this.log(`إرسال وضع تعليم الجمل: ${sentencesMetadata.mode}`);
      const r = await this.apiStartVoiceAgent(identity, fullName, userId, roomName, sentencesMetadata);
      roomName = r.room_name;
      if (this.elements.room) this.elements.room.value = roomName;
      
      this.log('غرفة تعلم الجمل جاهزة: ' + roomName, 'ok');
      
      if (r.dispatched) {
        this.log('Friday جاهز لتعليم الجمل ✔️', 'ok');
      }

      this.log('جاري الاتصال...');
      const { token, url } = await this.getLivekitToken(identity, roomName, userId);
      
      this.log('الاتصال بـ LiveKit...');
      this.room = new this.Room({
        adaptiveStream: true,
        dynacast: true,
        disconnectOnPageLeave: true,
        // إعدادات WebRTC لدعم جميع المتصفحات
        rtcConfig: {
          iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' },
            { urls: 'stun:stun2.l.google.com:19302' },
            { urls: 'stun:stun.services.mozilla.com' }
          ],
          iceTransportPolicy: 'all',
          bundlePolicy: 'max-bundle',
          rtcpMuxPolicy: 'require'
        }
      });

      this.setupRoomEvents();
      
      await this.room.connect(url, token);
      this.log('تم الاتصال بنجاح! ابدأ التحدث...', 'ok');
      
      // إعداد وتفعيل الميكروفون
      try {
        const mic = await this.createLocalAudioTrack();
        await this.room.localParticipant.publishTrack(mic);
        this.log('تم تفعيل الميكروفون 🎤', 'ok');
      } catch (micError) {
        this.log('تعذر تفعيل الميكروفون: ' + micError.message, 'err');
        console.error('Microphone error:', micError);
      }
      
      // رسالة ترحيب خاصة بالجمل
      setTimeout(() => {
        this.addMessage(
          'مرحباً بك في جلسة تعلم الجمل! سنتعلم معاً 10 جمل إنجليزية بسيطة. تحدث معي وسأساعدك في النطق والفهم.',
          'assistant'
        );
      }, 1000);
      
    } catch (error) {
      this.log('خطأ في الاتصال: ' + error.message, 'err');
      if (this.elements.joinBtn) this.elements.joinBtn.disabled = false;
      if (this.elements.leaveBtn) this.elements.leaveBtn.disabled = true;
    }
  }

  async leave() {
    try {
      if (this.room) {
        await this.room.disconnect();
        this.room = null;
      }
      
      if (this.elements.joinBtn) this.elements.joinBtn.disabled = false;
      if (this.elements.leaveBtn) this.elements.leaveBtn.disabled = true;
      
      this.log('تم قطع الاتصال', 'ok');
      this.addMessage('تم إنهاء جلسة تعلم الجمل. شكراً لك!', 'assistant');
      
    } catch (error) {
      this.log('خطأ في قطع الاتصال: ' + error.message, 'err');
    }
  }

  setupRoomEvents() {
    // باقي الدوال مثل client.js
    this.room.on(this.RoomEvent.TrackSubscribed, (track, publication, participant) => {
      if (track.kind === 'audio') {
        track.attach(this.audioEl);
        this.log(`تم استلام الصوت من ${participant.identity}`);
      }
    });

    this.room.on(this.RoomEvent.TrackUnsubscribed, (track) => {
      if (track.kind === 'audio') {
        track.detach();
      }
    });

    this.room.on(this.RoomEvent.DataReceived, (payload, participant, kind, topic) => {
      if (!participant) return;
      
      try {
        const message = JSON.parse(new TextDecoder().decode(payload));
        const isUser = participant.identity !== 'sci-agent';
        
        if (message.type === 'transcription') {
          this.handleTranscription(message.text, isUser, message.is_final);
        }
      } catch (error) {
        console.error('خطأ في معالجة البيانات:', error);
      }
    });

    this.room.on(this.RoomEvent.TranscriptionReceived, (segments, participant, publication) => {
      if (!participant) return;
      
      const isUser = participant.identity !== 'sci-agent';
      
      for (const segment of segments) {
        if (segment.text && segment.text.trim()) {
          this.handleTranscription(segment.text, isUser, segment.final);
        }
      }
    });

    this.room.registerTextStreamHandler('lk.transcription', async (reader, participantInfo) => {
      const message = await reader.readAll();
      const isUser = participantInfo.identity !== 'sci-agent';
      
      if (this.transcriptionTimeout) {
        clearTimeout(this.transcriptionTimeout);
        this.transcriptionTimeout = null;
      }
      
      if (reader.info.attributes['lk.transcribed_track_id']) {
        // النسخ المباشر
        if (isUser) {
          this.updateLiveTranscription(message, true);
          this.lastUserText = message;
          
          this.transcriptionTimeout = setTimeout(() => {
            this.finalizeTranscription(this.lastUserText, true);
          }, 2000);
          
        } else {
          this.updateLiveTranscription(message, false);
          this.lastAssistantText = message;
          
          this.transcriptionTimeout = setTimeout(() => {
            this.finalizeTranscription(this.lastAssistantText, false);
          }, 1500);
        }
        
      } else {
        // رسالة نهائية
        if (message && message.trim()) {
          this.finalizeTranscription(message, isUser);
        }
      }
    });

    this.room.on(this.RoomEvent.Disconnected, () => {
      this.log('تم قطع الاتصال من الغرفة');
      if (this.elements.joinBtn) this.elements.joinBtn.disabled = false;
      if (this.elements.leaveBtn) this.elements.leaveBtn.disabled = true;
    });
  }

  handleTranscription(message, isUser, isFinal = false) {
    if (!message || !message.trim()) return;
    
    if (!isFinal) {
      // نسخ مباشر
      this.updateLiveTranscription(message, isUser);
    } else {
      // رسالة نهائية
      this.finalizeTranscription(message, isUser);
    }
  }

  updateLiveTranscription(text, isUser) {
    if (this.elements.transcriptionText) {
      const icon = isUser ? '🎤' : '🤖';
      this.elements.transcriptionText.innerHTML = `${icon} ${text}`;
    }
  }

  finalizeTranscription(text, isUser) {
    if (text && text.trim()) {
      this.addMessage(text, isUser ? 'user' : 'assistant');
      this.log(`تم إضافة رسالة ${isUser ? 'مستخدم' : 'مساعد'}: ${text.substring(0, 50)}...`);
      
      this.updateLiveTranscription('جاري الاستماع...', false);
      
      if (isUser) {
        this.lastUserText = '';
      } else {
        this.lastAssistantText = '';
        this.showTyping(false);
      }
    }
  }

  // === API Functions ===
  async apiStartVoiceAgent(username, fullName, userId, roomName, metadata = {}) {
    const requestBody = {
      username: username,
      full_name: fullName,
      user_id: userId,
      room_name: roomName,
      mode: metadata.mode || 'normal'  // إضافة الوضع كحقل مباشر
    };
    
    console.log('طلب بدء العامل الصوتي:', requestBody);
    
    const response = await fetch('/api/start_voice_agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    });
    
    return await response.json();
  }

  async getLivekitToken(identity, roomName, userId) {
    const response = await fetch('/api/livekit/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: identity,
        room_name: roomName,
        user_id: userId
      })
    });
    
    return await response.json();
  }

  // === Helper Functions ===
  log(msg, cls = '') {
    // طباعة في console فقط
    const timestamp = new Date().toLocaleTimeString();
    const prefix = cls ? `[${cls.toUpperCase()}]` : '[INFO]';
    console.log(`${prefix} ${timestamp}: ${msg}`);
  }

  randName() {
    return "متعلم" + Math.floor(Math.random() * 1000);
  }
}

// تهيئة العميل عند تحميل الصفحة
window.addEventListener('DOMContentLoaded', () => {
  window.sentencesClient = new SentencesLearningClient();
});
