// dashboard.js
document.addEventListener('DOMContentLoaded', () => {

    document.querySelectorAll('.btn-manage').forEach(btn => {
        btn.addEventListener('click', function () {
            const id = this.dataset.id;
            const originalHTML = this.innerHTML;

            this.innerHTML = '加载中…';
            this.disabled = true;
            this.style.opacity = '0.7';

            setTimeout(() => {
                window.location.href = `/dashboard/server/${id}`;
            }, 350);
        });
    });

});