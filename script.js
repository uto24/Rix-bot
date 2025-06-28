document.addEventListener('DOMContentLoaded', () => {
    const tg = window.Telegram.WebApp;
    // --- ডিবাগিং এর জন্য ---
    tg.MainButton.setText('Close App').show().onClick(() => tg.close());

    // অ্যাপটি সম্পূর্ণ স্ক্রিনে দেখানোর জন্য
    tg.ready();
    tg.expand();

    // DOM এলিমেন্টগুলো সিলেক্ট করা
    const welcomeMessage = document.getElementById('welcome-message');
    const balanceAmount = document.getElementById('balance-amount');
    const miningStatus = document.getElementById('mining-status');
    const claimButton = document.getElementById('claim-button');
    const countdownTimer = document.getElementById('countdown-timer');
    let countdownInterval;

    // ব্যবহারকারীর নাম দেখানো
    if (tg.initDataUnsafe.user) {
        welcomeMessage.innerText = `Hi, ${tg.initDataUnsafe.user.first_name}!`;
    }

    // ডেটা রিকোয়েস্ট করার ফাংশন
    function requestUserData() {
        // বটকে একটি খালি ডেটা না পাঠিয়ে একটি অবজেক্ট পাঠানো ভালো অভ্যাস
        tg.sendData(JSON.stringify({ action: 'get_user_data' }));
    }

    // যখন অ্যাপটি প্রথম লোড হয় বা আবার ফোকাসে আসে, তখন ডেটা রিফ্রেশ হয়
    tg.onEvent('viewportChanged', () => {
        if (tg.isExpanded) {
            requestUserData();
        }
    });
    
    // প্রথমবার লোড হওয়ার সময় ডেটা রিকোয়েস্ট করুন
    requestUserData();

    // বট থেকে ডেটা পাওয়ার জন্য ইভেন্ট লিসেনার
    tg.onEvent('web_app_data_received', (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data) {
                updateUI(data);
            }
        } catch (e) {
            console.error("Error parsing data from bot:", e);
            miningStatus.innerText = "Error loading data. Please try again.";
        }
    });

    // UI আপডেট করার ফাংশন
    function updateUI(data) {
        if (countdownInterval) clearInterval(countdownInterval);

        balanceAmount.innerText = `${data.rix_balance || 0} RiX`;

        if (data.can_claim) {
            miningStatus.innerText = 'Your mining reward is ready!';
            claimButton.innerText = `Claim ${data.mining_reward} RiX`;
            claimButton.disabled = false;
            countdownTimer.innerText = '';
        } else {
            miningStatus.innerText = 'Next claim is in:';
            claimButton.disabled = true;
            claimButton.innerText = 'Come back later';
            startCountdown(data.next_claim_in_seconds || 0);
        }
    }

    // কাউন্টডাউন টাইমার শুরু করার ফাংশন
    function startCountdown(seconds) {
        let remaining = seconds;
        countdownInterval = setInterval(() => {
            if (remaining <= 0) {
                clearInterval(countdownInterval);
                requestUserData();
                return;
            }
            const h = Math.floor(remaining / 3600).toString().padStart(2, '0');
            const m = Math.floor((remaining % 3600) / 60).toString().padStart(2, '0');
            const s = (remaining % 60).toString().padStart(2, '0');
            countdownTimer.innerText = `${h}:${m}:${s}`;
            remaining--;
        }, 1000);
    }

    // ক্লেইম বাটনে ক্লিকের জন্য ইভেন্ট লিসেনার
    claimButton.addEventListener('click', () => {
        claimButton.disabled = true;
        claimButton.innerText = 'Claiming...';
        tg.sendData(JSON.stringify({ action: 'claim_from_mini_app' }));
    });
});
