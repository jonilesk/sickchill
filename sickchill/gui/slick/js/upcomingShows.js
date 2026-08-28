// Loads the TVmaze premiere cards into #upcomingShows and handles the list picker.
//
// This lives in its own file rather than in the addShows namespace in core.js, because core.js is
// only served when settings.DEVELOPER is on -- every other install gets core.min.js, a build
// artifact regenerated only by `grunt uglify:core`. An implementation in core.js alone would leave
// this page permanently blank on a normal install with nothing in the console to explain it, since
// UTIL.exec skips silently when the action is missing. trendingShows.js sets the precedent for
// shipping page JS as its own file.
(function () {
    const load = listKind => {
        $('#upcomingShows').loadRemoteShows(
            '/addShows/getUpcomingShows/?list=' + listKind,
            'Loading upcoming shows...',
            'TVmaze timed out, refresh page to try again',
        );
    };

    // core.js defines $.fn.loadRemoteShows inside its locale $.getJSON callback, so it does not
    // exist yet when this script is parsed. Wait for it instead of racing it.
    const start = () => {
        if (typeof $ === 'undefined' || typeof $.fn.loadRemoteShows !== 'function') {
            setTimeout(start, 50);
            return;
        }

        load($('#listKind').val());

        $('#listselection').on('change', event => {
            const listKind = event.target.value;
            window.history.replaceState({}, document.title, '?list=' + listKind);
            $('#listKind').val(listKind);
            load(listKind);
        });
    };

    start();
})();
