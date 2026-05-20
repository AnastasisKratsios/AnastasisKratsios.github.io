(function () {
	var duration = 2800;
	var animationFrame = null;
	var resetTimer = null;

	function ensureDistortionFilter() {
		if (document.getElementById('perfect-day-liquid-distortion')) {
			return;
		}

		var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
		svg.setAttribute('class', 'perfect-day-svg-filters');
		svg.setAttribute('aria-hidden', 'true');
		svg.setAttribute('focusable', 'false');
		svg.innerHTML = '<filter id="perfect-day-liquid-distortion" x="-30%" y="-30%" width="160%" height="160%">' +
			'<feTurbulence id="perfect-day-liquid-noise" type="fractalNoise" baseFrequency="0.02 0.08" numOctaves="4" seed="11" result="noise" />' +
			'<feDisplacementMap id="perfect-day-liquid-map" in="SourceGraphic" in2="noise" scale="0" xChannelSelector="R" yChannelSelector="G" />' +
			'</filter>';
		document.body.appendChild(svg);
	}

	function animateDistortion(startTime) {
		var noise = document.getElementById('perfect-day-liquid-noise');
		var map = document.getElementById('perfect-day-liquid-map');
		if (!noise || !map) {
			return;
		}

		function frame(now) {
			var t = Math.min(1, (now - startTime) / duration);
			var pulse = Math.sin(Math.PI * t);
			var violentPulse = Math.pow(pulse, 0.42);
			var chatter = Math.sin(t * Math.PI * 34) * 0.5 + Math.sin(t * Math.PI * 73) * 0.5;
			var scale = 8 + 155 * violentPulse + 22 * chatter * pulse;
			var baseX = 0.018 + 0.14 * pulse + 0.018 * Math.sin(t * 41);
			var baseY = 0.065 + 0.24 * pulse + 0.022 * Math.cos(t * 53);

			map.setAttribute('scale', Math.max(0, scale).toFixed(2));
			noise.setAttribute('baseFrequency', baseX.toFixed(4) + ' ' + baseY.toFixed(4));
			noise.setAttribute('seed', String(7 + Math.floor(t * 45)));

			if (t < 1 && document.body.classList.contains('screen-melt-active')) {
				animationFrame = window.requestAnimationFrame(frame);
			} else {
				map.setAttribute('scale', '0');
				noise.setAttribute('baseFrequency', '0.02 0.08');
			}
		}

		animationFrame = window.requestAnimationFrame(frame);
	}

	function triggerScreenMelt() {
		ensureDistortionFilter();

		if (animationFrame) {
			window.cancelAnimationFrame(animationFrame);
		}
		if (resetTimer) {
			window.clearTimeout(resetTimer);
		}

		document.body.classList.remove('screen-melt-active');
		void document.body.offsetWidth;
		document.body.classList.add('screen-melt-active');
		animateDistortion(performance.now());

		resetTimer = window.setTimeout(function () {
			document.body.classList.remove('screen-melt-active');
		}, duration + 120);
	}

	document.addEventListener('DOMContentLoaded', function () {
		var perfectDayImage = document.querySelector('.perfect-day-footer img');

		if (!perfectDayImage) {
			return;
		}

		perfectDayImage.addEventListener('click', triggerScreenMelt);
	});
})();
