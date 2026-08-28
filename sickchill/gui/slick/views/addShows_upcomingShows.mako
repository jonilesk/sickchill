<%inherit file="/layouts/main.mako" />
<%!
    from sickchill import settings
    from sickchill.oldbeard.helpers import anon_url
%>
<%block name="content">
    <div id="tabs">
        <div class="row">
            <div class="col-md-12">
                % if not header is UNDEFINED:
                    <h1 class="header">${header}</h1>
                % else:
                    <h1 class="title">${title}</h1>
                % endif
            </div>
        </div>
        <div class="row">
            <div class="col-md-12 text-center">
                <label for="showsort">
                    <span>${_('Sort By')}:</span>
                </label>

                <select id="showsort" class="form-control form-control-inline input-sm" title="Show Sort">
                    <option value="original" selected>${_('Air Date')}</option>
                    <option value="name">${_('Name')}</option>
                    <option value="rating">% ${_('Rating')}</option>
                    <option value="rank">${_('Popularity')}</option>
                </select>
                <label for="showsortdirection">
                    <span>${_('Sort Order')}:</span>
                </label>

                <select id="showsortdirection" class="form-control form-control-inline input-sm" title="Show Sort Direction">
                    <option value="asc" selected>${_('Asc')}</option>
                    <option value="desc">${_('Desc')}</option>
                </select>
                <label for="listselection">
                    <span>${_('Show')}:</span>
                </label>

                <select id="listselection" class="form-control form-control-inline input-sm" title="Premiere List Selection">
                    % for list_kind, list_title in list_options.items():
                        <option value="${list_kind}" ${selected(listKind == list_kind)}>${list_title}</option>
                    % endfor
                </select>
            </div>
            <div class="clearfix"></div>
            <div id="upcomingShows"></div>
            <input type="hidden" name="listKind" id="listKind" value="${listKind}" />
        </div>
        <div class="row">
            <div class="col-md-12 text-center" style="margin-top:20px">
                <p>
                    ## Only premieres that already have a TheTVDB id can be listed, because SickChill
                    ## stores shows by their TheTVDB id. Say so rather than implying full coverage.
                    <i>${_('Only premieres that TheTVDB already knows about can be listed here, so a show may appear closer to its air date.')}</i>
                </p>
                <p>
                    ## CC BY-SA 4.0 requires attribution, so this link is a licence condition.
                    <i>${_('Data provided by')} <a href="${anon_url('https://www.tvmaze.com/')}" target="_blank" rel="noreferrer">TVmaze</a></i>
                </p>
            </div>
        </div>
    </div>
</%block>

<%block name="scripts">
    <script type="text/javascript" src="${static_url('js/upcomingShows.js')}"></script>
</%block>
