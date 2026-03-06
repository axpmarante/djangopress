/**
 * Style Prompt Tools — tag chips + enhance button for instruction textareas.
 * Auto-initializes on DOMContentLoaded for all .style-prompt-tools containers.
 */
(function() {
    function init() {
        document.querySelectorAll('.style-prompt-tools').forEach(function(container) {
            var targetId = container.dataset.target;
            var textarea = document.getElementById(targetId);
            if (!textarea) return;

            // Tag chip click: append/remove tag text
            container.querySelectorAll('.style-tag').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var tag = btn.dataset.tag;
                    var current = textarea.value.trim();
                    var escaped = tag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    var regex = new RegExp('(^|[,;.\\s])' + escaped + '([,;.\\s]|$)', 'i');
                    if (regex.test(current)) {
                        textarea.value = current.replace(regex, '$1').replace(/\s{2,}/g, ' ').replace(/^[,;.\s]+|[,;.\s]+$/g, '').trim();
                        btn.classList.remove('border-purple-500', 'text-purple-700', 'bg-purple-50');
                        btn.classList.add('border-gray-300', 'text-gray-600');
                    } else {
                        textarea.value = current ? current + ', ' + tag : tag;
                        btn.classList.add('border-purple-500', 'text-purple-700', 'bg-purple-50');
                        btn.classList.remove('border-gray-300', 'text-gray-600');
                    }
                    textarea.focus();
                });
            });

            // Enhance button
            var enhanceBtn = container.querySelector('.style-enhance-btn');
            if (enhanceBtn) {
                enhanceBtn.addEventListener('click', function() {
                    var text = textarea.value.trim();
                    if (!text) return;

                    var origHTML = enhanceBtn.innerHTML;
                    enhanceBtn.innerHTML = '<span class="animate-pulse">Enhancing...</span>';
                    enhanceBtn.disabled = true;

                    var csrfToken = '';
                    var csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
                    if (csrfInput) csrfToken = csrfInput.value;
                    else {
                        var match = document.cookie.match(/csrftoken=([^;]+)/);
                        if (match) csrfToken = match[1];
                    }

                    fetch('/ai/api/enhance-prompt/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken,
                        },
                        body: JSON.stringify({ text: text, mode: 'enhance' }),
                    })
                    .then(function(res) { return res.json(); })
                    .then(function(data) {
                        if (data.success && data.text) {
                            textarea.value = data.text;
                        }
                    })
                    .catch(function(err) {
                        console.error('Enhance failed:', err);
                    })
                    .finally(function() {
                        enhanceBtn.innerHTML = origHTML;
                        enhanceBtn.disabled = false;
                        textarea.focus();
                    });
                });
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
