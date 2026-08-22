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
	var interactionMode = "repel";
	var state = letters.map(function () {
		return {
			x: 0, y: 0, r: 0, sx: 1, sy: 1,
			tx: 0, ty: 0, tr: 0, tsx: 1, tsy: 1
		};
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
				state[i].tsx = 1;
				state[i].tsy = 1;
				return;
			}

			if (interactionMode === "stretch") {
				var nx = (pointer.x - window.innerWidth / 2) / Math.max(1, window.innerWidth / 2);
				var ny = (pointer.y - window.innerHeight / 2) / Math.max(1, window.innerHeight / 2);

				state[i].tx = 0;
				state[i].ty = 0;
				state[i].tr = 0;

				/* Cursor position elastically stretches/contracts the word. */
				state[i].tsx = Math.max(0.55, Math.min(1.55, 1 + 0.48 * nx));
				state[i].tsy = Math.max(0.60, Math.min(1.45, 1 - 0.38 * ny));
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
			state[i].tsx = 1;
			state[i].tsy = 1;
		});
	}

	function animateLetters() {
		var moving = false;

		letters.forEach(function (letter, i) {
			var s = state[i];
			s.x += (s.tx - s.x) * 0.16;
			s.y += (s.ty - s.y) * 0.16;
			s.r += (s.tr - s.r) * 0.16;
			s.sx += (s.tsx - s.sx) * 0.14;
			s.sy += (s.tsy - s.sy) * 0.14;

			if (
				Math.abs(s.tx - s.x) > 0.05 ||
				Math.abs(s.ty - s.y) > 0.05 ||
				Math.abs(s.tr - s.r) > 0.02 ||
				Math.abs(s.tsx - s.sx) > 0.002 ||
				Math.abs(s.tsy - s.sy) > 0.002
			) moving = true;

			letter.style.transform =
				"translate3d(" + s.x.toFixed(2) + "px," + s.y.toFixed(2) + "px,0) " +
				"rotate(" + s.r.toFixed(2) + "deg) " +
				"scale(" + s.sx.toFixed(3) + "," + s.sy.toFixed(3) + ")";
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

		/* Fresh 50/50 interaction choice every time the hidden lander opens. */
		interactionMode = Math.random() < 0.5 ? "repel" : "stretch";

		pointer.inside = false;
		setTargets();
		ensureAnimation();

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
