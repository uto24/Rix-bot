document.addEventListener('DOMContentLoaded', () => {
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    const welcomeMessage = document.getElementById('welcome-message');
    const balanceAmount = document.getElementById('balance-amount');
    const miningStatus = document.getElementById('mining-status');
    const claimButton = document.getElementById('claim-button');
    const countdownTimer = document.getElementById('countdown-timer');
    let countdownInterval;

    if (tg.initDataUnsafe.user) {
        welcomeMessage.innerText = `Hi, ${tg.initDataUnsafe.user.first_name}!`;
    }

    // অ্যাপটি খোলা বা ফোকাসে থাকলে ডেটার জন্য রিকোয়েস্ট পাঠাও
    function requestUserData() {
        tg.sendData(JSON.stringify({ action: 'get_user_data' }));
    }

    // যখন অ্যাপটি প্রথম লোড হয় বা আবার ফোকাসে আসে, তখন ডেটা রিফ্রেশ হয়
    function onViewportChanged() {
        if (tg.isExpanded) {
            requestUserData();
        }
    }
    tg.onEvent('viewportChanged', onViewportChanged);
    onViewportChanged(); // প্রথমবার লোড হওয়ার সময় কল করুন

    // answer_web_app_query থেকে ডেটা পাওয়ার জন্য ইভেন্ট লিসেনার
    tg.onEvent('web_app_data_received', (event) => {
        try {
            const data = JSON.parse(event.data);
            updateUI(data);
        } catch (e) {
            console.error("Error parsing data from bot:", e);
            miningStatus.innerText = "Error loading data. Please try again.";
        }
    });

    function updateUI(data) {
        if (countdownInterval) clearInterval(countdownInterval);

        balanceAmount.innerText = `${data.rix_balance} RiX`;

        if (data.can_claim) {
            miningStatus.innerText = 'Your mining reward is ready!';
            claimButton.innerText = `Claim ${data.mining_reward} RiX`;
            claimButton.disabled = false;
            countdownTimer.innerText = '';
        } else {
            miningStatus.innerText = 'Next claim is in:';
            claimButton.disabled = true;
            claimButton.innerText = 'Come back later';
            startCountdown(data.next_claim_in_seconds);
        }
    }

    function startCountdown(seconds) {
        let remaining = seconds;
        countdownInterval = setInterval(() => {
            if (remaining <= 0) {
                clearInterval(countdownInterval);
                requestUserData(); // টাইমার শেষ হলে ডেটা আবার রিফ্রেশ করুন
                return;
            }
            const h = Math.floor(remaining / 3600).toString().padStart(2, '0');
            const m = Math.floor((remaining % 3600) / 60).toString().padStart(2, '0');
            const s = (remaining % 60).toString().padStart(2, '0');
            countdownTimer.innerText = `${h}:${m}:${s}`;
            remaining--;
        }, 1000);
    }

    claimButton.addEventListener('click', () => {
        claimButton.disabled = true;
        claimButton.innerText = 'Claiming...';
        tg.sendData(JSON.stringify({ action: 'claim_from_mini_app' }));
    });
});
