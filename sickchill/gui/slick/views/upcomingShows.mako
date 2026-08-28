<%inherit file="/layouts/main.mako" />
<%!
    from sickchill import settings
    from sickchill.oldbeard.helpers import anon_url
%>
<%block name="metas">
    <meta data-var="settings.SORT_ARTICLE" data-content="${settings.SORT_ARTICLE}">
    <meta data-var="settings.GRAMMAR_ARTICLES" data-content="${settings.GRAMMAR_ARTICLES}">
</%block>
<%block name="content">
    <div id="container">
        % if not upcoming_shows:
            <div class="trakt_show" style="width:100%; margin-top:20px">
                <p class="red-text">${_('TVmaze returned no upcoming premieres. Check your network connection and the SickChill log.')}</p>
            </div>
        % else:
            % for cur_show in upcoming_shows:
                <%
                    already_added = cur_show['tvdb_id'] in in_show_list
                    rating = int((cur_show['rating'] or 0) * 10)
                    air_date = cur_show['airdate'] or cur_show['airstamp'][:10]
                    channel = cur_show['network'] or _('Unknown')
                %>
                <div class="trakt_show" data-name="${cur_show['name'] | h}"
                     data-rating="${rating}" data-votes="${cur_show['weight'] or 0}"
                     data-rank="${cur_show['weight'] or 0}">
                    <div class="traktContainer">
                        <div class="trakt-image">
                            ## The img is deliberately NOT class="trakt-image": $.loadTraktImages()
                            ## selects img.trakt-image and, finding no data-src-indexer-id, would set
                            ## src to the undefined data-src-cache and blank the poster. The CSS still
                            ## applies, because the rule matches on ".trakt-image img" by descent.
                            <a class="trakt-image" href="${anon_url(cur_show['tvmaze_url'])}" target="_blank"
                               rel="noreferrer" title="${_('View on TVmaze')}">
                                % if cur_show['image_url']:
                                    <img alt="${cur_show['name'] | h}" class="trakt-image-static"
                                         src="${cur_show['image_url'] | h}" loading="lazy"
                                         height="273px" width="186px" />
                                % else:
                                    <img alt="${cur_show['name'] | h}" class="trakt-image-static"
                                         src="${static_url('images/trakt-placeholder.png')}"
                                         height="273px" width="186px" />
                                % endif
                            </a>
                        </div>

                        <div class="show-title">
                            ${cur_show['name'] | h}
                        </div>

                        <div class="clearfix">
                            <p>${air_date | h}</p>
                            <i>${channel | h}</i>
                            % if cur_show['season'] and cur_show['kind'] == 'season':
                                <i>&nbsp;&mdash;&nbsp;${_('Season')} ${cur_show['season']}</i>
                            % endif
                            <div class="traktShowTitleIcons">
                                % if already_added:
                                    <span class="btn btn-xs disabled">${_('Already added')}</span>
                                % else:
                                    <a href="${scRoot}/addShows/addShowByID?indexer_id=${cur_show['tvdb_id']}&amp;show_name=${cur_show['name'] | u}"
                                       class="btn btn-xs">${_('Add Show')}</a>
                                % endif
                            </div>
                        </div>
                    </div>
                </div>
            % endfor
        % endif
    </div>
</%block>
