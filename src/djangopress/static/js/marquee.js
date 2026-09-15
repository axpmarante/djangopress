/* dp-marquee initializer.
 *
 * For each .dp-marquee on the page, clone the .dp-marquee-track children once
 * (marking clones with aria-hidden="true" + data-editor-skip="true") so the
 * translateX(-50%) keyframe animation loops seamlessly.
 *
 * The editor v2 filters elements with data-editor-skip="true" when computing
 * nth-child selectors and when listing editable images, so clones never enter
 * the stored HTML and never appear as duplicate entries in the editor UI.
 */
(function () {
    'use strict';

    function setup(marquee) {
        if (marquee.dataset.dpMarqueeReady === '1') return;
        var track = marquee.querySelector(':scope > .dp-marquee-track');
        if (!track) return;

        var originals = Array.prototype.filter.call(track.children, function (c) {
            return c.getAttribute('aria-hidden') !== 'true'
                && c.getAttribute('data-editor-skip') !== 'true';
        });
        if (originals.length === 0) return;

        originals.forEach(function (orig) {
            var clone = orig.cloneNode(true);
            clone.setAttribute('aria-hidden', 'true');
            clone.setAttribute('data-editor-skip', 'true');
            if (clone.tagName === 'IMG') clone.setAttribute('alt', '');
            clone.querySelectorAll && clone.querySelectorAll('img').forEach(function (img) {
                img.setAttribute('alt', '');
                img.setAttribute('aria-hidden', 'true');
            });
            track.appendChild(clone);
        });

        var speed = marquee.dataset.marqueeSpeed;
        if (speed) {
            var dur = /^\d+(\.\d+)?$/.test(speed) ? speed + 's' : speed;
            track.style.setProperty('--dp-marquee-duration', dur);
        }

        marquee.dataset.dpMarqueeReady = '1';
    }

    function init() {
        document.querySelectorAll('.dp-marquee').forEach(setup);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
