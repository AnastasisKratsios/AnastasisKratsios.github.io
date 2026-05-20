(function () {
	function triggerScreenMelt() {
		document.body.classList.remove('screen-melt-active');
		void document.body.offsetWidth;
		document.body.classList.add('screen-melt-active');

		window.setTimeout(function () {
			document.body.classList.remove('screen-melt-active');
		}, 1950);
	}

	document.addEventListener('DOMContentLoaded', function () {
		var perfectDay = document.querySelector('.perfect-day-footer');

		if (!perfectDay) {
			return;
		}

		perfectDay.addEventListener('click', triggerScreenMelt);
	});
})();
