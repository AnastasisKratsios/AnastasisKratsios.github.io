(function () {
	"use strict";

	document.addEventListener("DOMContentLoaded", function () {
		var perfectDayImage = document.querySelector(".perfect-day-footer img");

		if (!perfectDayImage) return;

		perfectDayImage.addEventListener("click", function () {
			document.body.classList.remove("screen-melt-active");

			// Restart the animation if the image is clicked repeatedly.
			void document.body.offsetWidth;

			document.body.classList.add("screen-melt-active");

			window.setTimeout(function () {
				document.body.classList.remove("screen-melt-active");
			}, 1900);
		});
	});
})();
