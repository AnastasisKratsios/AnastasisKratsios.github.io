(function () {
	"use strict";

	var trigger = document.getElementById("perfect-day-trigger");
	var lander = document.getElementById("ai-lander");
	var landerImage = document.getElementById("ai-lander-bg-image");
	var landerVideo = document.getElementById("ai-lander-bg-video");
	var pageBackground = document.getElementById("scroll-background");
	var pageVideo = document.getElementById("scroll-background-video");
	var letters = lander ? Array.prototype.slice.call(lander.querySelectorAll(".ai-lander-letter")) : [];

	if (!trigger || !lander || !landerImage || !landerVideo || !pageBackground) return;

	var pointer = { x: -10000, y: -10000, inside: false };
	var state = letters.map(function () {
		return { x: 0, y: 0, r: 0, tx: 0, ty: 0, tr: 0 };
	});
	var animationFrame = null;

	function syncChosenBackground() {
		var videoSrc = pageVideo && (pageVideo.currentSrc || pageVideo.getAttribute("src"));
		var videoVisible = pageVideo && window.getComputedStyle(pageVideo).display !== "none" && videoSrc;

		if (videoVisible) {
			landerImage.style.backgroundImage = "none";
			landerVideo.src = videoSrc;
			landerVideo.style.display = "block";
			landerVideo.currentTime = pageVideo.currentTime || 0;
			landerVideo.play().catch(function () {});
		} else {
			landerVideo.pause();
			landerVideo.removeAttribute("src");
			landerVideo.load();
			landerVideo.style.display = "none";

			var chosenImage = pageBackground.style.backgroundImage ||
				window.getComputedStyle(pageBackground).backgroundImage;
			landerImage.style.backgroundImage = chosenImage;
		}
	}

	function setTargets() {
		var radius = Math.min(window.innerWidth, window.innerHeight) * 0.46;

		letters.forEach(function (letter, i) {
			if (!pointer.inside) {
				state[i].tx = 0;
				state[i].ty = 0;
				state[i].tr = 0;
				return;
			}

			var rect = letter.getBoundingClientRect();
			var cx = rect.left + rect.width / 2;
			var cy = rect.top + rect.height / 2;
			var dx = cx - pointer.x;
			var dy = cy - pointer.y;
			var distance = Math.sqrt(dx * dx + dy * dy) || 1;
			var influence = Math.max(0, 1 - distance / radius);
			var force = 105 * influence * influence;

			state[i].tx = (dx / distance) * force;
			state[i].ty = (dy / distance) * force;
			state[i].tr = (pointer.x - cx) / Math.max(1, window.innerWidth) * -9 * influence;
		});
	}

	function animateLetters() {
		var moving = false;

		letters.forEach(function (letter, i) {
			var s = state[i];
			s.x += (s.tx - s.x) * 0.16;
			s.y += (s.ty - s.y) * 0.16;
			s.r += (s.tr - s.r) * 0.16;

			if (
				Math.abs(s.tx - s.x) > 0.05 ||
				Math.abs(s.ty - s.y) > 0.05 ||
				Math.abs(s.tr - s.r) > 0.02
			) moving = true;

			letter.style.transform =
				"translate3d(" + s.x.toFixed(2) + "px," + s.y.toFixed(2) + "px,0) " +
				"rotate(" + s.r.toFixed(2) + "deg)";
		});

		animationFrame = (moving || pointer.inside)
			? window.requestAnimationFrame(animateLetters)
			: null;
	}

	function ensureAnimation() {
		if (animationFrame === null) {
			animationFrame = window.requestAnimationFrame(animateLetters);
		}
	}

	function openLander(event) {
		if (event) {
			event.preventDefault();
			event.stopPropagation();
		}

		syncChosenBackground();
		lander.hidden = false;
		lander.setAttribute("aria-hidden", "false");
		document.body.classList.add("ai-lander-open");

		window.requestAnimationFrame(function () {
			lander.classList.add("is-open");
		});
	}

	function closeLander() {
		lander.classList.remove("is-open");
		lander.setAttribute("aria-hidden", "true");
		document.body.classList.remove("ai-lander-open");
		pointer.inside = false;
		setTargets();
		ensureAnimation();

		window.setTimeout(function () {
			if (!lander.classList.contains("is-open")) {
				lander.hidden = true;
				landerVideo.pause();
			}
		}, 190);
	}

	trigger.addEventListener("click", openLander);

	lander.addEventListener("click", function (event) {
		event.preventDefault();
		event.stopPropagation();
		closeLander();
	});

	lander.addEventListener("pointermove", function (event) {
		pointer.x = event.clientX;
		pointer.y = event.clientY;
		pointer.inside = true;
		setTargets();
		ensureAnimation();
	}, { passive: true });

	lander.addEventListener("pointerleave", function () {
		pointer.inside = false;
		setTargets();
		ensureAnimation();
	}, { passive: true });

	window.addEventListener("resize", function () {
		if (!lander.hidden) {
			setTargets();
			ensureAnimation();
		}
	});
})();
