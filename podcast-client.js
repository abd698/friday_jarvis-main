class PodcastManager {
    constructor() {
        this.room = null;
        this.voiceAgent = null;
        this.isConnected = false;
        this.isConnecting = false;
        this.audioAnalyzer = null;
        this.statusEl = document.getElementById('status');
        this.startBtn = document.getElementById('startBtn');
        this.stopBtn = document.getElementById('stopBtn');
        this.audioLevelBar = document.getElementById('audioLevelBar');
        this.transcriptionText = document.getElementById('transcriptionText');
        this.transcriptionIndicator = document.getElementById('transcriptionIndicator');
        this.chatBox = document.getElementById('chatBox');
        
        // متغيرات LiveKit
        this.Room = null;
        this.RoomEvent = null;
        this.createLocalAudioTrack = null;
        
        // متغيرات الصوت والرسائل
        this.audioEl = null;
        this.currentUserMessage = null;
        this.currentAssistantMessage = null;
        this.lastUserText = '';
        this.lastAssistantText = '';
        
        this.init();
    }

    async init() {
        await this.setupLiveKit();
        this.setupAudio();
        this.initializeEventListeners();
    }

    async setupLiveKit() {
        try {
            let LiveKitModule;
            
            // جرّب script tag أولاً
            if (window.LivekitClient) {
                console.log('[podcast] ✅ LiveKit محمل من script tag');
                LiveKitModule = window.LivekitClient;
            } else {
                // Fallback: dynamic import
                console.log('[podcast] 🔄 محاولة dynamic import...');
                try {
                    LiveKitModule = await import('https://cdn.jsdelivr.net/npm/livekit-client@2.15.4/dist/livekit-client.esm.mjs');
                } catch (err) {
                    LiveKitModule = await import('https://unpkg.com/livekit-client@2.15.4/dist/livekit-client.esm.mjs');
                }
            }
            
            const { Room, RoomEvent, createLocalAudioTrack, setLogLevel, LogLevel } = LiveKitModule;
            
            setLogLevel(LogLevel.warn);
            this.Room = Room;
            this.RoomEvent = RoomEvent;
            this.createLocalAudioTrack = createLocalAudioTrack;
            
            console.log('[podcast] ✅ تم تحميل LiveKit بنجاح');
        } catch (error) {
            console.error('[podcast] ❌ خطأ في تحميل LiveKit:', error);
            alert('خطأ في تحميل مكتبة المحادثة\nالرجاء إعادة تحميل الصفحة');
            throw error;
        }
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

    initializeEventListeners() {
        this.startBtn.addEventListener('click', () => this.startConversation());
        this.stopBtn.addEventListener('click', () => this.stopConversation());
    }

    updateStatus(message, type = 'default') {
        this.statusEl.textContent = message;
        this.statusEl.className = 'status';
        if (type === 'connected') {
            this.statusEl.classList.add('connected');
        } else if (type === 'error') {
            this.statusEl.classList.add('error');
        }
    }

    updateAudioLevel(level) {
        if (this.audioLevelBar) {
            this.audioLevelBar.style.width = `${level * 100}%`;
        }
    }

    async startConversation() {
        if (this.isConnecting || this.isConnected) return;

        try {
            this.isConnecting = true;
            this.startBtn.disabled = true;
            this.updateStatus('📡 جاري الاتصال بخدمة المحادثة...', 'default');

            // التحقق من المصادقة والحصول على معلومات المستخدم
            const authToken = localStorage.getItem('access_token');
            const userData = localStorage.getItem('user_data');
            const userEmail = localStorage.getItem('user_email');
            const userName = localStorage.getItem('user_name');
            
            console.log('[podcast] فحص بيانات المستخدم: ✅ تمت المصادقة');
            
            if (!authToken && !userData && !userEmail) {
                this.updateStatus('❌ يرجى تسجيل الدخول أولاً', 'error');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 2000);
                return;
            }

            // إعداد معلومات الجلسة
            const roomName = 'english-conversation-' + Math.floor(Math.random() * 10000);
            let identity, fullName, userId;
            
            if (userData) {
                try {
                    const user = JSON.parse(userData);
                    identity = user.username || user.email || 'متعلم' + Math.floor(Math.random() * 1000);
                    fullName = user.full_name || user.username || user.email || identity;
                    userId = user.id || user.user_id;
                    console.log('[podcast] استخدام بيانات من user_data:', { identity, fullName, userId });
                } catch (e) {
                    console.error('[podcast] خطأ في تحليل user_data:', e);
                    identity = userName || userEmail || 'متعلم' + Math.floor(Math.random() * 1000);
                    fullName = userName || identity;
                    userId = null;
                }
            } else {
                identity = userName || userEmail || 'متعلم' + Math.floor(Math.random() * 1000);
                fullName = userName || identity;
                userId = null;
                console.log('[podcast] استخدام البيانات المحلية:', { identity, fullName, userId });
            }

            console.log('[podcast] بدء جلسة المحادثة الإنجليزية مع البيانات:', {
                identity, fullName, userId, roomName
            });
            
            // بدء جلسة صوتية مع وضع المحادثة الإنجليزية
            const agentResponse = await fetch('/api/start_voice_agent', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username: identity,
                    full_name: fullName,
                    user_id: userId,
                    room_name: roomName,
                    mode: 'english_conversation'
                })
            });

            if (!agentResponse.ok) {
                throw new Error(`خطأ في بدء العامل الصوتي: ${agentResponse.status}`);
            }

            const agentData = await agentResponse.json();
            console.log('[podcast] استجابة العامل الصوتي:', agentData);
            
            this.updateStatus('🔑 جاري الحصول على توكن الوصول...', 'default');

            // الحصول على توكن LiveKit (تم توحيد المسار)
            const tokenResponse = await fetch('/api/livekit/token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username: identity,
                    room_name: agentData.room_name || roomName,
                    user_id: userId
                })
            });

            if (!tokenResponse.ok) {
                throw new Error(`خطأ في الحصول على التوكن: ${tokenResponse.status}`);
            }

            const tokenData = await tokenResponse.json();
            console.log('[podcast] بيانات التوكن:', tokenData);

            this.updateStatus('🔗 جاري الاتصال بالغرفة الصوتية...', 'default');

            // الاتصال بغرفة LiveKit
            await this.connectToRoom(tokenData.token, agentData.room_name || roomName, tokenData.url);

        } catch (error) {
            console.error('[podcast] خطأ في بدء المحادثة:', error);
            this.updateStatus(`❌ خطأ في الاتصال: ${error.message}`, 'error');
            this.resetControls();
        }
    }

    async connectToRoom(token, roomName, wsUrl) {
        try {
            this.room = new this.Room({
                adaptiveStream: true,
                dynacast: true,
                disconnectOnPageLeave: true
            });

            this.setupRoomEvents();
            
            // الاتصال بالغرفة باستخدام URL المُرجع من الخادم
            await this.room.connect(wsUrl, token);
            
            console.log('[podcast] تم الاتصال بنجاح');
            this.isConnected = true;
            this.isConnecting = false;
            this.updateStatus('✅ متصل! يمكنك البدء بالتحدث الآن', 'connected');
            this.startBtn.disabled = true;
            this.stopBtn.disabled = false;
            
            // تفعيل الميكروفون
            try {
                const mic = await this.createLocalAudioTrack();
                await this.room.localParticipant.publishTrack(mic);
                console.log('[podcast] تم تفعيل الميكروفون');
                this.setupAudioAnalyzer();
            } catch (micError) {
                console.error('[podcast] خطأ في تفعيل الميكروفون:', micError);
            }
            
            // رسالة ترحيب
            setTimeout(() => {
                this.updateStatus('🤖 Friday جاهز للمحادثة! تحدث بالإنجليزية', 'connected');
                // رسالة تجريبية للتأكد من عمل الصناديق
                this.addChatMessage("Connected! I'm Friday, ready to practice English with you. Let's start!", false);
                this.updateLiveTranscription('جاري الاستماع...', true);
            }, 1000);

        } catch (error) {
            console.error('[podcast] خطأ في الاتصال بالغرفة:', error);
            this.updateStatus(`❌ خطأ في الاتصال: ${error.message}`, 'error');
            this.resetControls();
        }
    }

    setupRoomEvents() {
        this.room.on(this.RoomEvent.Connected, () => {
            console.log('[podcast] متصل بالغرفة');
        });

        this.room.on(this.RoomEvent.Disconnected, () => {
            console.log('[podcast] انقطع الاتصال');
            this.isConnected = false;
            this.updateStatus('📡 جاري التحضير للاتصال...', 'default');
            this.resetControls();
            this.cleanupAudioAnalyzer();
        });

        this.room.on(this.RoomEvent.ParticipantConnected, (participant) => {
            console.log('[podcast] انضم مشارك جديد:', participant.identity);
            if (participant.identity.includes('agent')) {
                this.voiceAgent = participant;
                this.updateStatus('🤖 Friday جاهز للمحادثة التفاعلية!', 'connected');
            }
        });

        this.room.on(this.RoomEvent.ParticipantDisconnected, (participant) => {
            console.log('[podcast] غادر مشارك:', participant.identity);
            if (participant === this.voiceAgent) {
                this.voiceAgent = null;
            }
        });

        this.room.on(this.RoomEvent.TrackSubscribed, (track, publication, participant) => {
            if (track.kind === 'audio') {
                // ربط الصوت بشكل صحيح مثل client.js
                const mediaStream = new MediaStream([track.mediaStreamTrack]);
                this.audioEl.srcObject = mediaStream;
                console.log('[podcast] ✅ تم ربط الصوت من:', participant.identity);
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
                console.error('[podcast] خطأ في معالجة البيانات:', error);
            }
        });

        // معالج النصوص المتدفقة (Text Stream)
        this.room.on(this.RoomEvent.TranscriptionReceived, (segments, participant, publication) => {
            if (!participant) return;
            
            const isUser = participant.identity !== 'sci-agent';
            
            for (const segment of segments) {
                if (segment.text && segment.text.trim()) {
                    this.handleTranscription(segment.text, isUser, segment.final);
                }
            }
        });
    }

    handleTranscription(message, isUser, isFinal = false) {
        if (!message || !message.trim()) return;
        
        console.log('[podcast] Transcription:', { message, isUser, isFinal });
        
        // تحديث النص المباشر
        if (!isFinal) {
            // نص مؤقت - يظهر في transcription box
            const prefix = isUser ? '👤 أنت: ' : '🤖 Friday: ';
            this.updateLiveTranscription(prefix + message, true);
        } else {
            // رسالة نهائية
            if (isUser) {
                if (message !== this.lastUserText) {
                    this.addChatMessage(message, true);
                    this.updateLiveTranscription('جاري الاستماع...', true);
                    this.lastUserText = message;
                }
            } else {
                if (message !== this.lastAssistantText) {
                    this.addChatMessage(message, false);
                    this.updateLiveTranscription('جاري الاستماع...', true);
                    this.lastAssistantText = message;
                }
            }
        }
    }

    updateLiveTranscription(text, isActive = false) {
        if (this.transcriptionText) {
            this.transcriptionText.textContent = text;
        }
        
        if (this.transcriptionIndicator) {
            if (isActive) {
                this.transcriptionIndicator.classList.add('active');
            } else {
                this.transcriptionIndicator.classList.remove('active');
            }
        }
    }

    addChatMessage(message, isUser) {
        if (!this.chatBox) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${isUser ? 'user' : 'assistant'}`;
        
        const label = document.createElement('div');
        label.className = 'message-label';
        label.textContent = isUser ? '👤 أنت' : '🤖 Friday';
        
        const content = document.createElement('div');
        content.className = 'message-content';
        content.textContent = message;
        
        messageDiv.appendChild(label);
        messageDiv.appendChild(content);
        this.chatBox.appendChild(messageDiv);
        
        // التمرير للرسالة الأحدث
        messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }

    setupAudioAnalyzer() {
        try {
            if (!this.room || !this.room.localParticipant) return;

            const audioTracks = this.room.localParticipant.audioTrackPublications;
            if (audioTracks.size === 0) {
                setTimeout(() => this.setupAudioAnalyzer(), 1000);
                return;
            }

            const audioTrack = Array.from(audioTracks.values())[0].track;
            if (!audioTrack || !audioTrack.mediaStreamTrack) return;

            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = audioContext.createMediaStreamSource(new MediaStream([audioTrack.mediaStreamTrack]));
            const analyzer = audioContext.createAnalyser();
            
            analyzer.fftSize = 256;
            source.connect(analyzer);

            const dataArray = new Uint8Array(analyzer.frequencyBinCount);
            
            const updateLevel = () => {
                if (!this.isConnected) return;
                
                analyzer.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) {
                    sum += dataArray[i];
                }
                const average = sum / dataArray.length;
                const level = Math.min(average / 128, 1);
                
                this.updateAudioLevel(level);
                requestAnimationFrame(updateLevel);
            };

            updateLevel();
            this.audioAnalyzer = { audioContext, analyzer };
            console.log('[podcast] تم إعداد محلل الصوت');

        } catch (error) {
            console.error('[podcast] خطأ في إعداد محلل الصوت:', error);
        }
    }

    cleanupAudioAnalyzer() {
        if (this.audioAnalyzer) {
            try {
                this.audioAnalyzer.audioContext.close();
            } catch (error) {
                console.error('[podcast] خطأ في إغلاق AudioContext:', error);
            }
            this.audioAnalyzer = null;
        }
        this.updateAudioLevel(0);
    }

    async stopConversation() {
        try {
            this.updateStatus('🔌 جاري قطع الاتصال...', 'default');
            
            if (this.room) {
                await this.room.disconnect();
                this.room = null;
            }
            
            this.voiceAgent = null;
            this.isConnected = false;
            this.isConnecting = false;
            
            this.cleanupAudioAnalyzer();
            this.resetControls();
            this.updateStatus('📡 جاري التحضير للاتصال...', 'default');
            
        } catch (error) {
            console.error('[podcast] خطأ في إيقاف المحادثة:', error);
            this.updateStatus(`❌ خطأ في قطع الاتصال: ${error.message}`, 'error');
        }
    }

    resetControls() {
        this.startBtn.disabled = false;
        this.stopBtn.disabled = true;
        this.isConnecting = false;
    }
}

// تهيئة مدير البودكاست عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', () => {
    console.log('[podcast] تم تحميل صفحة المحادثة الإنجليزية');
    
    // فحص جميع بيانات المصادقة
    const token = localStorage.getItem('access_token');
    const userData = localStorage.getItem('user_data');
    const userEmail = localStorage.getItem('user_email');
    const userName = localStorage.getItem('user_name');
    
    console.log('[podcast] فحص بيانات المصادقة:');
    console.log('- access_token:', token ? 'موجود' : 'غير موجود');
    console.log('- user_data:', userData ? 'موجود' : 'غير موجود');
    console.log('- user_email:', userEmail ? userEmail : 'غير موجود');
    console.log('- user_name:', userName ? userName : 'غير موجود');
    
    // فحص المصادقة - يكفي وجود access_token أو user_data
    if (!token && !userData && !userEmail) {
        console.log('[podcast] لا توجد بيانات مصادقة');
        alert('يرجى تسجيل الدخول أولاً قبل استخدام ميزة المحادثة الإنجليزية');
        window.location.href = '/login';
        return;
    }
    
    console.log('[podcast] بيانات المصادقة متوفرة، يتم تهيئة المدير...');
    
    const podcastManager = new PodcastManager();
    
    // حفظ المرجع في window للوصول إليه من وحدة التحكم
    window.podcastManager = podcastManager;
});

// معالج لمنع إغلاق الصفحة أثناء المحادثة
window.addEventListener('beforeunload', (event) => {
    if (window.podcastManager && window.podcastManager.isConnected) {
        event.preventDefault();
        event.returnValue = 'هل أنت متأكد من إغلاق المحادثة؟';
        return 'هل أنت متأكد من إغلاق المحادثة؟';
    }
});
