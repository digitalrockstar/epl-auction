(function () {
    var KEY_MUTE = "epl_sound_muted";
    function isMuted() { try { return localStorage.getItem(KEY_MUTE) === "1"; } catch (e) { return false; } }
    function setMuted(v) {
        try { localStorage.setItem(KEY_MUTE, v ? "1" : "0"); } catch (e) {}
        document.querySelectorAll(".snd-mute-btn").forEach(function (b) { b.textContent = v ? "\uD83D\uDD07" : "\uD83D\uDD0A"; });
    }

    var ctx;
    function actx() { if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)(); return ctx; }

    function tone(freq, dur, type, vol, delay) {
        if (isMuted()) return;
        try {
            var c = actx(), t0 = c.currentTime + (delay || 0);
            var osc = c.createOscillator(), gain = c.createGain();
            osc.type = type || "sine";
            osc.frequency.setValueAtTime(freq, t0);
            gain.gain.setValueAtTime(0, t0);
            gain.gain.linearRampToValueAtTime(vol || 0.2, t0 + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
            osc.connect(gain).connect(c.destination);
            osc.start(t0); osc.stop(t0 + dur + 0.02);
        } catch (e) {}
    }

    function sweep(f1, f2, dur, type, vol) {
        if (isMuted()) return;
        try {
            var c = actx(), t0 = c.currentTime;
            var osc = c.createOscillator(), gain = c.createGain();
            osc.type = type || "sawtooth";
            osc.frequency.setValueAtTime(f1, t0);
            osc.frequency.exponentialRampToValueAtTime(f2, t0 + dur);
            gain.gain.setValueAtTime(0, t0);
            gain.gain.linearRampToValueAtTime(vol || 0.15, t0 + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
            osc.connect(gain).connect(c.destination);
            osc.start(t0); osc.stop(t0 + dur + 0.02);
        } catch (e) {}
    }

    var pool = {};
    function playFile(src) {
        if (isMuted()) return;
        try {
            var a = pool[src];
            if (!a) { a = new Audio(src); pool[src] = a; }
            a.currentTime = 0;
            a.play().catch(function () {});
        } catch (e) {}
    }

    var prefs = window.EPL_SOUND_PREFS || { bid: "classic", result: "classic", timer: "tick", roll: "whoosh" };

    var EPLSound = {
        isMuted: isMuted,
        setMuted: setMuted,
        toggleMute: function () { setMuted(!isMuted()); },

        playBid: function () {
            if (prefs.bid === "off") return;
            if (prefs.bid === "classic") playFile("/static/sfx/bid.mp3");
            else tone(880, 0.12, "square", 0.15);
        },
        playSold: function () {
            if (prefs.result === "off") return;
            if (prefs.result === "classic") playFile("/static/sfx/sold.mp3");
            else sweep(400, 1200, 0.5, "sine", 0.2);
        },
        playUnsold: function () {
            if (prefs.result === "off") return;
            if (prefs.result === "classic") playFile("/static/sfx/unsold.mp3");
            else sweep(500, 150, 0.5, "sawtooth", 0.2);
        },
        playTimerTick: function () {
            if (prefs.timer === "off") return;
            if (prefs.timer === "beep") tone(1200, 0.08, "square", 0.12);
            else tone(700, 0.06, "sine", 0.1);
        },
        playTimerAlarm: function () {
            if (prefs.timer === "off") return;
            tone(220, 0.35, "sawtooth", 0.25);
            tone(220, 0.35, "sawtooth", 0.25, 0.4);
        },
        playRollSpin: function () {
            if (prefs.roll === "off") return;
            if (prefs.roll === "chime") { tone(600, 0.15, "triangle", 0.15); tone(900, 0.15, "triangle", 0.15, 0.15); }
            else sweep(200, 800, 1.2, "sawtooth", 0.08);
        },
        playRollStop: function () {
            if (prefs.roll === "off") return;
            tone(1000, 0.2, "triangle", 0.2);
        },

        _lastTick: null,
        _lastBid: {},
        onTimerTick: function (seconds) {
            if (seconds === null || seconds === undefined || isNaN(seconds)) return;
            if (this._lastTick === seconds) return;
            this._lastTick = seconds;
            if (seconds === 0) { this.playTimerAlarm(); return; }
            if (seconds > 0 && seconds <= 10) this.playTimerTick();
        },
        onBidMarker: function (key, bidValue) {
            if (bidValue === null || bidValue === undefined || bidValue === "") return;
            var prev = this._lastBid[key];
            if (prev !== undefined && prev !== bidValue) this.playBid();
            this._lastBid[key] = bidValue;
        }
    };
    window.EPLSound = EPLSound;

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".snd-mute-btn").forEach(function (b) {
            b.textContent = isMuted() ? "\uD83D\uDD07" : "\uD83D\uDD0A";
            b.addEventListener("click", function () { EPLSound.toggleMute(); });
        });
    });

    document.addEventListener("htmx:afterSwap", function (e) {
        var el = e.detail && e.detail.target;
        if (!el) return;

        var timerEl = el.querySelector ? el.querySelector("[data-seconds]") : null;
        if (timerEl) EPLSound.onTimerTick(parseInt(timerEl.dataset.seconds, 10));

        var bidEl = el.querySelector ? el.querySelector("#admin-bid-marker, #mgr-bid-marker") : null;
        if (bidEl) EPLSound.onBidMarker(bidEl.id, bidEl.dataset.bid);
    });
})();
