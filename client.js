/**
 * SCI Voice Chat Client - JavaScript Functions
 * ملف JavaScript منفصل لجميع وظائف واجهة المحادثة الصوتية
 */

class SCIVoiceClient {
  constructor() {
    this.authToken = null;
    this.authEmail = null;
    this.userName = null;
    this.room = null;
    this.audioEl = null;
    
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

  async init() {
    // تهيئة عناصر DOM
    this.initElements();
    
    // إعداد الصوت
    this.setupAudio();
    
    // استعادة الجلسة
    this.restoreSession();
    
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
      'joinBtn', 'leaveBtn', 'room', 'name', 'signoutBtn', 'userInfo',
      'chatMessages', 'typingIndicator', 'liveTranscription', 
      'transcriptionText', 'transcriptionIndicator', 'sentences3000Btn', 'podcastBtn',
      'feedbackCard', 'starRating', 'feedbackText', 'submitFeedbackBtn', 'skipFeedbackBtn', 'feedbackSuccess',
      'connectionLoader'
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
      this.audioEl.muted = false; // التأكد من عدم كتم الصوت
      this.audioEl.volume = 1.0;
      this.audioEl.style.display = 'none';
      document.body.appendChild(this.audioEl);
    } else {
      this.audioEl.autoplay = true;
      this.audioEl.playsInline = true;
      this.audioEl.muted = false;
      this.audioEl.volume = 1.0;
    }
    
    // إعدادات الميكروفون المحسّنة
    this.audioConstraints = {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      sampleRate: 48000
    };
  }

  async setupLiveKit() {
    try {
      // تحقق من تحميل LiveKit من script tag
      if (typeof window.LivekitClient !== 'undefined') {
        this.log('✅ تم تحميل LiveKit من script tag', 'ok');
        
        const { Room, RoomEvent, createLocalAudioTrack, setLogLevel, LogLevel } = window.LivekitClient;
        
        setLogLevel(LogLevel.warn);
        this.Room = Room;
        this.RoomEvent = RoomEvent;
        this.createLocalAudioTrack = createLocalAudioTrack;
        
        // إنشاء room object
        this.room = new Room({ adaptiveStream: false, dynacast: false });
        this.setupRoomEvents();
        
        return; // نجاح!
      }
      
      // Fallback: محاولة dynamic import
      this.log('🔄 جاري محاولة dynamic import...', 'warn');
      
      const cdnUrls = [
        'https://cdn.jsdelivr.net/npm/livekit-client@2.15.4/dist/livekit-client.esm.mjs',
        'https://unpkg.com/livekit-client@2.15.4/dist/livekit-client.esm.mjs'
      ];
      
      for (const url of cdnUrls) {
        try {
          this.log(`🔄 تحميل من: ${url.split('/')[2]}...`);
          
          const { Room, RoomEvent, createLocalAudioTrack, setLogLevel, LogLevel } = 
            await import(url);
          
          setLogLevel(LogLevel.warn);
          this.Room = Room;
          this.RoomEvent = RoomEvent;
          this.createLocalAudioTrack = createLocalAudioTrack;
          
          this.log(`✅ نجاح من: ${url.split('/')[2]}`, 'ok');
          
          this.room = new Room({ adaptiveStream: false, dynacast: false });
          this.setupRoomEvents();
          
          return;
          
        } catch (err) {
          console.warn(`Failed: ${url}`, err);
        }
      }
      
      // فشلت جميع المحاولات
      throw new Error('Failed to load LiveKit from all sources');
      
    } catch (error) {
      this.log('❌ فشل تحميل LiveKit', 'err');
      alert('خطأ في تحميل مكتبة المحادثة\n\nالرجاء:\n1. إعادة تحميل الصفحة (F5)\n2. استخدام Chrome\n3. تعطيل Proxy/VPN');
      console.error('LiveKit setup error:', error);
    }
  }

  setupRoomEvents() {
    this.room.on(this.RoomEvent.Connected, () => {
      this.log('تم الاتصال بالغرفة ✅', 'ok');
      this.updateLiveTranscription('متصل - جاري الاستماع...', true);
    });

    this.room.on(this.RoomEvent.Disconnected, () => {
      this.log('تم قطع الاتصال', 'warn');
      this.updateLiveTranscription('غير متصل', false);
    });

    this.room.on(this.RoomEvent.TrackPublished, (publication, participant) => {
      if (publication.kind === 'audio') {
        if (participant.identity === 'sci-agent') {
          this.showTyping(true);
          this.log('المساعد يتحدث...', 'info');
        } else {
          this.updateLiveTranscription('جاري التحدث...', true);
        }
      }
      this.log(`تم نشر مسار ${publication.kind} من ${participant.identity}`);
    });

    this.room.on(this.RoomEvent.TrackUnpublished, (publication, participant) => {
      if (publication.kind === 'audio') {
        if (participant.identity === 'sci-agent') {
          this.showTyping(false);
        } else {
          this.updateLiveTranscription('جاري الاستماع...', true);
        }
      }
      this.log(`تم إلغاء نشر مسار ${publication.kind} من ${participant.identity}`);
    });

    this.room.on(this.RoomEvent.LocalTrackPublished, (pub) => {
      this.log(`تم نشر الميكروفون محليًا (${pub.kind})`);
    });

    this.room.on(this.RoomEvent.ActiveSpeakersChanged, (speakers) => {
      const names = speakers.map((s) => s.identity).join(', ');
      if (names) this.log('المتحدثون النشطون: ' + names);
    });

    this.room.on(this.RoomEvent.TrackSubscribed, async (track, _pub, participant) => {
      if (track.kind === 'audio') {
        this.log(`اشتراك صوت من: ${participant.identity}`, 'ok');
        
        try {
          const mediaStream = new MediaStream([track.mediaStreamTrack]);
          this.audioEl.srcObject = mediaStream;
          this.audioEl.volume = 1.0; // مستوى الصوت كامل
          
          // تشغيل صريح (ضروري لبعض المتصفحات)
          const playPromise = this.audioEl.play();
          
          if (playPromise !== undefined) {
            await playPromise;
            this.log('🔊 يتم تشغيل صوت Agent', 'ok');
          }
        } catch (playError) {
          console.error('[audio play error]', playError);
          this.log('⚠️ فشل تشغيل الصوت - اضغط في أي مكان للتفعيل', 'warn');
          
          // إعادة محاولة عند أي ضغطة
          document.body.addEventListener('click', async () => {
            try {
              await this.audioEl.play();
              this.log('✅ تم تفعيل الصوت', 'ok');
            } catch (e) {
              console.error('[retry play error]', e);
            }
          }, { once: true });
        }
      }
    });

    // معالج النص المتدفق
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
          this.updateLiveTranscription(`🎤 ${message}`, true);
          this.lastUserText = message;
          
          this.transcriptionTimeout = setTimeout(() => {
            this.finalizeTranscription(this.lastUserText, true);
          }, 2000);
          
        } else {
          this.updateLiveTranscription(`🤖 ${message}`, true);
          this.lastAssistantText = message;
          
          this.transcriptionTimeout = setTimeout(() => {
            this.finalizeTranscription(this.lastAssistantText, false);
          }, 1500);
        }
        
        this.log(`نسخ حي: ${message.substring(0, 30)}...`);
      } else {
        // رسالة نهائية
        if (message && message.trim()) {
          this.finalizeTranscription(message, isUser);
        }
      }
    });
  }

  setupEventListeners() {
    this.elements.joinBtn?.addEventListener('click', () => this.join());
    this.elements.leaveBtn?.addEventListener('click', () => this.leave());
    this.elements.signoutBtn?.addEventListener('click', () => this.doSignout());
    this.elements.sentences3000Btn?.addEventListener('click', () => this.goTo3000Sentences());
    this.elements.podcastBtn?.addEventListener('click', () => this.goToPodcast());
    
    // 🌟 Feedback System
    this.setupFeedbackSystem();
    
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
      
      if (this.elements.joinBtn) this.elements.joinBtn.disabled = false;
      if (this.elements.signoutBtn) this.elements.signoutBtn.disabled = false;
    } else {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user_email');
      localStorage.removeItem('user_name');
      localStorage.removeItem('user_data');
      
      if (this.elements.userInfo) {
        this.elements.userInfo.textContent = 'غير مسجل الدخول';
      }
      
      if (this.elements.joinBtn) this.elements.joinBtn.disabled = true;
      if (this.elements.signoutBtn) this.elements.signoutBtn.disabled = true;
    }
  }

  restoreSession() {
    this.setAuth(
      localStorage.getItem('access_token'), 
      localStorage.getItem('user_email'),
      localStorage.getItem('user_name')
    );
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

  updateMessage(messageDiv, newContent) {
    if (messageDiv && messageDiv.querySelector('.message-content')) {
      messageDiv.querySelector('.message-content').textContent = newContent;
      this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    }
  }

  showTyping(show = true) {
    if (this.elements.typingIndicator) {
      this.elements.typingIndicator.style.display = show ? 'block' : 'none';
      if (show && this.elements.chatMessages) {
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
      }
    }
  }

  updateLiveTranscription(text, isActive = false) {
    if (this.elements.transcriptionText) {
      this.elements.transcriptionText.textContent = text || 'جاري الاستماع...';
    }
    
    if (this.elements.liveTranscription) {
      this.elements.liveTranscription.classList.toggle('active', isActive);
    }
    
    if (this.elements.transcriptionIndicator) {
      this.elements.transcriptionIndicator.classList.toggle('active', isActive);
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

  // === وظائف الاتصال ===
  async join() {
    try {
      // 🔄 إظهار مؤشر التحميل
      if (this.elements.connectionLoader) this.elements.connectionLoader.style.display = 'flex';
      
      if (this.elements.joinBtn) this.elements.joinBtn.disabled = true;
      if (this.elements.leaveBtn) this.elements.leaveBtn.disabled = false;

      // توليد اسم غرفة جديد دائماً لتجنب مشاكل إعادة الاتصال
      let roomName = null; // دع الخادم ينشئ غرفة جديدة
      const identity = this.elements.name?.value.trim() || this.randName();
      const fullName = localStorage.getItem('user_name') || identity;
      const userId = localStorage.getItem('user_data') ? 
        JSON.parse(localStorage.getItem('user_data')).user_id : null;

      if (!this.authToken) {
        throw new Error('يرجى تسجيل الدخول أولاً');
      }

      this.log('تهيئة العامل وإجراء dispatch...');
      
      // 🎤 استخراج الصوت المختار من المتغير العام (معرّف في client.html)
      const voiceName = typeof selectedVoice !== 'undefined' ? selectedVoice : 'Aoede';
      this.log(`إرسال بيانات المستخدم: الاسم="${identity}", الاسم الكامل="${fullName}", معرف المستخدم="${userId}", الصوت="${voiceName}"`);
      
      const r = await this.apiStartVoiceAgent(identity, fullName, userId, roomName, voiceName);
      roomName = r.room_name;
      if (this.elements.room) this.elements.room.value = roomName;
      
      this.log('الغرفة جاهزة: ' + roomName, 'ok');
      
      if (r.dispatched) {
        this.log('تم إرسال العامل الصوتي (sci-agent) إلى الغرفة ✔️', 'ok');
      } else if (r.dispatch_error) {
        this.log('تعذر إرسال العامل: ' + r.dispatch_error + ' — سنعيد المحاولة مرة واحدة...', 'err');
        await new Promise((res) => setTimeout(res, 1000));
        const r2 = await this.apiStartVoiceAgent(identity, fullName, userId, roomName, voiceName);  // 🎤 مع الصوت
        if (r2.dispatched) {
          this.log('إعادة المحاولة نجحت: تم إرسال العامل ✔️', 'ok');
        } else {
          this.log('إعادة المحاولة فشلت أيضاً: ' + (r2.dispatch_error || 'غير معروف'), 'err');
        }
      }

      this.log('طلب توكن...');
      const { token, url } = await this.getLivekitToken(identity, roomName, userId);
      this.log('الاتصال بالسيرفر...');
      await this.room.connect(url, token);
      this.log('تم الاتصال بنجاح ✅', 'ok');

      // إنشاء مسار صوتي محلي بإعدادات محسّنة
      const mic = await this.createLocalAudioTrack({
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      });
      
      await this.room.localParticipant.publishTrack(mic);
      this.log('تم تفعيل الميكروفون 🎤', 'ok');
      
      // التأكد من أن الميكروفون غير مكتوم
      if (mic.isMuted) {
        await mic.unmute();
        this.log('🎵 تم إلغاء كتم الميكروفون', 'ok');
      }
      
      // ✅ إخفاف مؤشر التحميل بعد النجاح
      if (this.elements.connectionLoader) this.elements.connectionLoader.style.display = 'none';
    } catch (e) {
      console.error('[join error]', e);
      
      // رسالة خطأ واضحة حسب نوع الخطأ
      let errorMsg = 'خطأ في الاتصال';
      
      if (e.message && e.message.includes('pc connection')) {
        errorMsg = 'فشل الاتصال بالسيرفر\nالرجاء إعادة المحاولة';
      } else if (e.message && e.message.includes('leave request')) {
        errorMsg = 'تم قطع الاتصال من السيرفر';
      }
      
      this.log(errorMsg, 'err');
      
      // تنظيف
      if (this.room) {
        try {
          await this.room.disconnect();
        } catch (disconnectErr) {
          console.error('[disconnect error]', disconnectErr);
        }
      }
      
      // ❗ إخفاء المؤشر في حالة الخطأ
      if (this.elements.connectionLoader) this.elements.connectionLoader.style.display = 'none';
      
      if (this.elements.joinBtn) this.elements.joinBtn.disabled = false;
      if (this.elements.leaveBtn) this.elements.leaveBtn.disabled = true;
    }
  }

  async leave() {
    try {
      await this.room.disconnect();
      this.updateLiveTranscription('غير متصل', false);
      this.showTyping(false);
    } finally {
      if (this.elements.joinBtn) this.elements.joinBtn.disabled = false;
      if (this.elements.leaveBtn) this.elements.leaveBtn.disabled = true;
      
      // 🌟 إظهار نموذج التقييم بعد إنهاء المحادثة
      setTimeout(() => {
        if (this.showFeedback) {
          this.showFeedback();
        }
      }, 1500);
    }
  }

  // === وظائف API ===
  async apiStartVoiceAgent(username, full_name = '', user_id = null, room_name = null, voice_name = 'Aoede') {
    const res = await fetch('/api/start_voice_agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, full_name, user_id, room_name, voice_name }),
    });
    if (!res.ok) throw new Error('فشل بدء العامل الصوتي: ' + res.status);
    return res.json();
  }

  async getLivekitToken(username, roomName, user_id = null) {
    const res = await fetch('/api/livekit/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, room_name: roomName, user_id }),
    });
    if (!res.ok) throw new Error('فشل طلب التوكن: ' + res.status);
    return res.json();
  }

  async authRequest(path, body) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    });
    let data;
    try { 
      data = await res.json(); 
    } catch { 
      data = await res.text(); 
    }
    return { ok: res.ok, status: res.status, data };
  }

  // === وظائف مساعدة ===
  log(msg, cls = '') {
    // طباعة في console فقط
    const prefix = cls ? `[${cls.toUpperCase()}]` : '[LOG]';
    console.log(`${prefix} ${msg}`);
    return;
    const div = document.createElement('div');
    div.className = cls;
    div.textContent = `${new Date().toLocaleTimeString()}: ${msg}`;
    targetLog.appendChild(div);
    targetLog.scrollTop = targetLog.scrollHeight;
  }

  sanitizeEmail(value) {
    if (!value) return '';
    let v = String(value);
    try { v = v.normalize('NFKC'); } catch {}
    const bidi = /[\u200E\u200F\u202A-\u202E\u2066-\u2069\u061C]/g;
    const zeroWidth = /[\u200B\u200C\u200D\uFEFF\u2060\u180E]/g;
    v = v.replace(bidi, '').replace(zeroWidth, '');
    v = v.replace(/[\u00A0\s]+/g, '');
    v = v.replace(/^["']+|["']+$/g, '');
    return v.trim().toLowerCase();
  }

  /* ملاحظة: تمت إزالة نسخ مكررة من الدوال authRequest و log في أسفل الملف.
     يُستخدم التعريف الأول الموجود سابقاً في الكلاس لتفادي التعارض. */

  randName() { 
    return "مستخدم" + Math.floor(Math.random() * 1000);
  }

  goTo3000Sentences() {
    console.log('تم النقر على زر 3000 جملة');
    try {
      // التنقل إلى صفحة 3000 جملة
      window.location.href = '/3000-sentences.html';
      console.log('تم التوجه إلى /3000-sentences.html');
    } catch (error) {
      console.error('خطأ في التنقل:', error);
      // طريقة بديلة للتنقل
      window.open('/3000-sentences.html', '_self');
    }
  }

  goToPodcast() {
    console.log('تم النقر على زر البودكاست');
    try {
      // التنقل إلى صفحة البودكاست
      window.location.href = '/podcast.html';
      console.log('تم التوجه إلى /podcast.html');
    } catch (error) {
      console.error('خطأ في التنقل:', error);
      // طريقة بديلة للتنقل
      window.open('/podcast.html', '_self');
    }
  }

  loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = (e) => reject(e);
      document.head.appendChild(s);
    });
  }

  sanitizeEmail(value) {
    return value.replace(/[^a-zA-Z0-9@._-]/g, '');
  }

  // === نظام جمع الآراء ===
  setupFeedbackSystem() {
    this.selectedRating = 0;
    
    // تقييم بالنجوم
    if (this.elements.starRating) {
      const stars = this.elements.starRating.querySelectorAll('i');
      
      stars.forEach((star, index) => {
        star.addEventListener('click', () => {
          this.selectedRating = index + 1;
          stars.forEach((s, i) => {
            s.classList.toggle('active', i < this.selectedRating);
          });
        });
        
        star.addEventListener('mouseenter', () => {
          stars.forEach((s, i) => {
            s.style.color = i <= index ? '#fbbf24' : 'rgba(255, 255, 255, 0.3)';
          });
        });
      });
      
      this.elements.starRating.addEventListener('mouseleave', () => {
        stars.forEach((s, i) => {
          if (!s.classList.contains('active')) {
            s.style.color = 'rgba(255, 255, 255, 0.3)';
          }
        });
      });
    }
    
    // إرسال التقييم
    if (this.elements.submitFeedbackBtn) {
      this.elements.submitFeedbackBtn.addEventListener('click', () => {
        this.submitFeedback();
      });
    }
    
    // تخطي
    if (this.elements.skipFeedbackBtn) {
      this.elements.skipFeedbackBtn.addEventListener('click', () => {
        this.hideFeedback();
      });
    }
  }
  
  showFeedback() {
    if (this.elements.feedbackCard) {
      this.elements.feedbackCard.style.display = 'block';
      this.elements.feedbackCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  
  hideFeedback() {
    if (this.elements.feedbackCard) {
      this.elements.feedbackCard.style.display = 'none';
    }
  }
  
  async submitFeedback() {
    const feedbackText = this.elements.feedbackText?.value || '';
    
    if (this.selectedRating === 0) {
      alert('الرجاء اختيار تقييم بالنجوم');
      return;
    }
    
    const feedback = {
      rating: this.selectedRating,
      comment: feedbackText,
      user_email: this.authEmail || 'anonymous',
      user_name: this.userName || 'anonymous',
      session_date: new Date().toISOString(),
      room: this.elements.room?.value || 'unknown'
    };
    
    console.log(`🌟 [INFO] ${new Date().toLocaleTimeString()}: تقييم: ${this.selectedRating} نجوم`);
    if (feedbackText) {
      console.log(`💬 [INFO] ${new Date().toLocaleTimeString()}: ${feedbackText}`);
    }
    
    try {
      // إرسال للسيرفر
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.authToken || ''}`
        },
        body: JSON.stringify(feedback)
      });
      
      if (response.ok) {
        // عرض رسالة النجاح
        if (this.elements.feedbackSuccess) {
          this.elements.feedbackSuccess.style.display = 'block';
          this.elements.submitFeedbackBtn.style.display = 'none';
          this.elements.skipFeedbackBtn.textContent = 'إغلاق';
        }
        
        setTimeout(() => {
          this.hideFeedback();
          this.resetFeedback();
        }, 3000);
      }
    } catch (error) {
      console.error('[ERR] خطأ في إرسال التقييم:', error);
      // إظهار النجاح حتى لو فشل لتحسين UX
      if (this.elements.feedbackSuccess) {
        this.elements.feedbackSuccess.style.display = 'block';
        this.elements.submitFeedbackBtn.style.display = 'none';
      }
      setTimeout(() => {
        this.hideFeedback();
        this.resetFeedback();
      }, 2000);
    }
  }
  
  resetFeedback() {
    this.selectedRating = 0;
    if (this.elements.feedbackText) {
      this.elements.feedbackText.value = '';
    }
    if (this.elements.starRating) {
      this.elements.starRating.querySelectorAll('i').forEach(s => {
        s.classList.remove('active');
        s.style.color = 'rgba(255, 255, 255, 0.3)';
      });
    }
    if (this.elements.feedbackSuccess) {
      this.elements.feedbackSuccess.style.display = 'none';
    }
    if (this.elements.submitFeedbackBtn) {
      this.elements.submitFeedbackBtn.style.display = '';
    }
    if (this.elements.skipFeedbackBtn) {
      this.elements.skipFeedbackBtn.textContent = 'تخطي';
    }
  }
}

// تهيئة العميل عند تحميل الصفحة
window.addEventListener('DOMContentLoaded', () => {
  window.sciClient = new SCIVoiceClient();
});
