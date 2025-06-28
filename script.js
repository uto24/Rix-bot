document.addEventListener('DOMContentLoaded', () => {
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand(); // অ্যাপটি সম্পূর্ণ স্ক্রিনে দেখানোর জন্য

    const welcomeMessage = document.getElementById('welcome-message');
    const balanceAmount = document.getElementById('balance-amount');
    const miningStatus = document.getElementById('mining-status');
    const claimButton = document.getElementById('claim-button');
    const countdownTimer = document.getElementById('countdown-timer');

    // ব্যবহারকারীর নাম দেখান
    if (tg.initDataUnsafe.user) {
        welcomeMessage.innerText = `Hi, ${tg.initDataUnsafe.user.first_name}!`;
    }

    // ব্যাকএন্ডে ডেটা পাঠানোর জন্য একটি অবজেক্ট
    let requestData = {
        action: 'get_user_data',
        user: tg.initDataUnsafe.user
    };
    
    // যখন অ্যাপ লোড হবে, তখন বটের কাছে ব্যবহারকারীর ডেটা চেয়ে একটি মেসেজ পাঠাবে
    tg.sendData(JSON.stringify(requestData));

    // বট থেকে ডেটা পাওয়ার জন্য ইভেন্ট লিসেনার
    tg.onEvent('web_app_data_received', (data) => {
        const response = JSON.parse(data.data);
        updateUI(response);
    });
    
    function updateUI(data) {
        // ব্যালেন্স আপডেট
        balanceAmount.innerText = `${data.rix_balance} RiX`;

        // মাইনিং স্ট্যাটাস আপডেট
        if (data.can_claim) {
            miningStatus.innerText = 'Your mining reward is ready!';
            claimButton.innerText = `Claim ${data.mining_reward} RiX`;
            claimButton.disabled = false;
            countdownTimer.innerText = '';
        } else {
            miningStatus.innerText = 'Next claim is in:';
            claimButton.disabled = true;
            startCountdown(data.next_claim_in_seconds);
        }
    }

    function startCountdown(seconds) {
        let remaining = seconds;
        const interval = setInterval(() => {
            if (remaining <= 0) {
                clearInterval(interval);
                miningStatus.innerText = 'Your mining reward is ready!';
                claimButton.disabled = false;
                countdownTimer.innerText = '';
                return;
            }
            const h = Math.floor(remaining / 3600).toString().padStart(2, '0');
            const m = Math.floor((remaining % 3600) / 60).toString().padStart(2, '0');
            const s = (remaining % 60).toString().padStart(2, '0');
            countdownTimer.innerText = `${h}:${m}:${s}`;
            remaining--;
        }, 1000);
    }
    
    // ক্লেইম বাটনে ক্লিক করলে
    claimButton.addEventListener('click', () => {
        // বটকে জানাও যে ক্লেইম করা হয়েছে
        tg.sendData(JSON.stringify({ action: 'claim_from_mini_app' }));
        tg.close(); // অ্যাপ বন্ধ করে দাও
    });
});
