// Load saved states when page loads
document.addEventListener('DOMContentLoaded', function () {
    // For each container, check if it was expanded
    document.querySelectorAll('.endpoint-container').forEach(container => {
        const path = container.getAttribute('data-path');
        const isExpanded = localStorage.getItem('expanded_' + path) === 'true';

        if (isExpanded) {
            container.classList.add('expanded');

            // Also load the data if it was expanded
            const refreshIcon = container.querySelector('.refresh-icon');
            if (refreshIcon) {
                // Trigger the htmx request
                htmx.trigger(refreshIcon, 'click');
            }
        }
    });

    // Set up lightbox overlay click handler
    document.getElementById('lightbox-overlay').addEventListener('click', function () {
        const fullsizeImages = document.querySelectorAll('.fullsize');
        fullsizeImages.forEach(img => {
            img.classList.remove('fullsize');
        });
        this.classList.remove('active');
    });

    // Set up image click handlers after content is loaded
    document.body.addEventListener('htmx:afterOnLoad', function () {
        setupImageHandlers();
    });
});

function setupImageHandlers() {
    document.querySelectorAll('.screenshot-img').forEach(img => {
        img.addEventListener('click', function (e) {
            const overlay = document.getElementById('lightbox-overlay');

            if (this.classList.contains('fullsize')) {
                this.classList.remove('fullsize');
                overlay.classList.remove('active');
            } else {
                this.classList.add('fullsize');
                overlay.classList.add('active');
                e.stopPropagation();
            }
        });
    });
}

function toggleSection(path, id) {
    const container = document.getElementById(id);
    const wasExpanded = container.classList.contains('expanded');
    container.classList.toggle('expanded');

    // Store state in localStorage
    localStorage.setItem('expanded_' + path, (!wasExpanded).toString());

    // If we're expanding and there's no content yet, trigger the refresh
    if (!wasExpanded && container.querySelector('.output-container').innerHTML.trim() === '') {
        const refreshIcon = container.querySelector('.refresh-icon');
        if (refreshIcon) {
            // Trigger the htmx request without the animation
            htmx.ajax('GET', refreshIcon.getAttribute('hx-get'), { target: refreshIcon.getAttribute('hx-target') });
        }
    }
}

function refreshData(event, containerId, refreshIconId, path) {
    event.stopPropagation();

    // Add spinning animation
    const refreshIcon = document.getElementById(refreshIconId);
    refreshIcon.classList.add('spinning');

    // Ensure container is expanded
    const container = document.getElementById(containerId);
    container.classList.add('expanded');

    // Save expanded state to localStorage
    localStorage.setItem('expanded_' + path, 'true');

    // Remove spinning after data loads
    document.getElementById(refreshIconId).addEventListener('htmx:afterOnLoad', function () {
        refreshIcon.classList.remove('spinning');
        setupImageHandlers(); // Set up image handlers after content loads
    }, { once: true });
}

(new EventSource("/updates")).onmessage = function (event) {
    let data = JSON.parse(event.data);
    let element = document.getElementById(`output-${data.id}`);
    element.innerHTML = data.rendered;
};
