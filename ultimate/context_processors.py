def menu_leagues(request):
	from ultimate.leagues.models import League

	leagues = League.objects.filter(state__in=['closed', 'open', 'preview']).order_by('league_start_date')
	leagues = [league for league in leagues if league.is_visible(request.user)]

	leagues.sort(key=lambda k: k.league_start_date.weekday())

	return {'menu_leagues': leagues}


def user_profile_is_complete(request):
	result = {'user_profile_is_complete': False}
	if request.user and request.user.is_authenticated():
		try:
			result['user_profile_is_complete'] = bool(request.user.get_profile().is_complete_for_user)
		except:
			return result

	return result


def user_rating_is_complete(request):
	result = {'user_rating_is_complete': False}
	if request.user and request.user.is_authenticated():
		try:
			result['user_rating_is_complete'] = bool(request.user.playerratings_set.filter(submitted_by=request.user, user=request.user))
		except:
			return result

	return result
