import copy
import csv
import re
from datetime import date, datetime, timedelta
from functools import reduce
from itertools import groupby
from math import ceil, floor

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.urlresolvers import reverse
from django.db.models import F, Q
from django.db.transaction import atomic
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template import RequestContext
from django.utils import timezone

from ultimate.forms import ScheduleGenerationForm

from ultimate.captain.models import GameReport
from ultimate.leagues.models import (
    FieldNames,
    Game,
    GameTeams,
    League,
    Registrations,
    Team,
    TeamMember,
)
from ultimate.user.models import Player, PlayerConcussionWaiver

from ultimate.utils.export_helpers import get_export_headers, get_export_values

from paypal.standard.ipn.models import PayPalIPN


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name="junta").exists())
def index(request):

    return render(request, "junta/index.html", {})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def concussion_compliance(request, player_user_id=None):
    leagues = League.objects.all().order_by("-league_start_date")
    leagues = [league for league in leagues if league.is_visible(request.user)]
    cutoff_year = date(timezone.now().year - 18, 1, 1)
    player = None

    registrations = (
        Registrations.objects.select_related("user")
        .filter(league__in=leagues, user__profile__date_of_birth__gte=cutoff_year)
        .order_by("user__last_name", "user__first_name", "league__league_start_date")
    )

    minor_registrations = [
        r
        for r in registrations
        if hasattr(r.user, "profile")
        and r.user.profile.is_minor(r.league.league_start_date)
        and r.is_complete
        and not r.waitlist
        and not r.refunded
    ]

    if player_user_id:
        try:
            player = get_user_model().objects.get(id=player_user_id)
        except get_user_model().DoesNotExist:
            player = None

    if request.method == "POST":
        if "approve" in request.POST:
            PlayerConcussionWaiver.objects.update_or_create(
                submitted_by=player,
                defaults={
                    "reviewed_at": timezone.now(),
                    "reviewed_by": request.user,
                    "status": PlayerConcussionWaiver.PLAYER_CONCUSSION_WAIVER_APPROVED,
                },
            )

        if "deny" in request.POST:
            PlayerConcussionWaiver.objects.update_or_create(
                submitted_by=player,
                defaults={
                    "reviewed_at": timezone.now(),
                    "reviewed_by": request.user,
                    "status": PlayerConcussionWaiver.PLAYER_CONCUSSION_WAIVER_DENIED,
                },
            )

        if "export" in request.POST:
            response = HttpResponse()
            response["Content-Disposition"] = (
                'attachment; filename="a2u_concusson_compliance.csv"'
            )

            writer = csv.writer(response)
            writer.writerow(
                [
                    "player",
                    "player email",
                    "guardian",
                    "guardian email",
                    "league",
                    "team",
                    "status",
                ]
            )

            for minor_registration in minor_registrations:
                writer.writerow(
                    [
                        minor_registration.user.get_full_name(),
                        minor_registration.user.email,
                        (
                            minor_registration.user.profile.guardian_name
                            if hasattr(minor_registration.user, "profile")
                            else ""
                        ),
                        (
                            minor_registration.user.profile.guardian_email
                            if hasattr(minor_registration.user, "profile")
                            else minor_registration.league
                        ),
                        minor_registration.league,
                        ",".join(
                            str(team_id)
                            for team_id in Team.objects.filter(
                                league=minor_registration.league,
                                teammember__user=minor_registration.user,
                            ).values_list("id", flat=True)
                        ),
                        minor_registration.user.concussion_waiver_status(),
                    ]
                )

            return response

    return render(
        request,
        "junta/concussion_compliance.html",
        {
            "leagues": leagues,
            "minor_registrations": minor_registrations,
            "player": player,
        },
    )


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name="junta").exists())
def captainstatus(request, year=None, season=None, division=None):
    league = None
    leagues = None

    if year and season and division:
        league = get_object_or_404(
            League,
            Q(year=year),
            Q(season__name=season) | Q(season__slug=season),
            Q(night=division) | Q(night_slug=division),
        )

    else:
        leagues = League.objects.all().order_by("-league_start_date")

    return render(
        request, "junta/captainstatus.html", {"league": league, "leagues": leagues}
    )


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name="junta").exists())
def leagueresults(request, year=None, season=None, division=None):
    leagues = None
    league = None
    game_locations = None
    game_dates = None
    team_records = None

    if year and season and division:
        league = get_object_or_404(
            League,
            Q(year=year),
            Q(season__name=season) | Q(season__slug=season),
            Q(night=division) | Q(night_slug=division),
        )
        games = league.game_set.order_by(
            "date", "start", "field_name", "field_name__field"
        )
        game_locations = league.get_game_locations(games=games)
        game_dates = league.get_game_dates(games=games, game_locations=game_locations)

        team_records = []
        for team in league.team_set.all():
            team_records.append(team.get_record_list())

        team_records = sorted(team_records, key=lambda k: k["wins"], reverse=True)

    else:
        leagues = League.objects.all().order_by("-league_start_date")

    return render(
        request,
        "junta/leagueresults.html",
        {
            "leagues": leagues,
            "league": league,
            "game_locations": game_locations,
            "game_dates": game_dates,
            "team_records": team_records,
        },
    )


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name="junta").exists())
def gamereports(
    request, year=None, season=None, division=None, game_id=None, team_id=None
):
    leagues = None
    league = None
    game = None
    team = None
    game_reports = None
    game_locations = None
    game_dates = None
    team_data = None

    if year and season and division:
        league = get_object_or_404(
            League,
            Q(year=year),
            Q(season__name=season) | Q(season__slug=season),
            Q(night=division) | Q(night_slug=division),
        )

        if game_id and team_id:
            game = get_object_or_404(Game, id=game_id)
            team = get_object_or_404(Team, id=team_id)
            game_reports = GameReport.objects.filter(team__id=team_id, game__id=game_id)

        else:
            game_reports = GameReport.objects.filter(
                team__league=league, game__league=league
            ).order_by("game__start", "team__id")

            if request.method == "POST":
                if "export" in request.POST:
                    response = HttpResponse()
                    response["Content-Disposition"] = (
                        'attachment; filename="' + league.__str__() + '.csv"'
                    )

                    writer = csv.writer(response)
                    writer.writerow(
                        [
                            "Date",
                            "Team",
                            "Players",
                            "Women Matchers",
                            "Man Matchers",
                            "Email",
                            "First Name",
                            "Last Name",
                            "Spirit",
                            "Comment",
                        ]
                    )

                    for game_report in game_reports:
                        for (
                            game_report_comment
                        ) in game_report.gamereportcomment_set.all():
                            writer.writerow(
                                [
                                    game_report.game.start,
                                    game_report.team.id,
                                    game_report.num_players_in_attendance,
                                    game_report.num_females_in_attendance,
                                    game_report.num_males_in_attendance,
                                    game_report_comment.submitted_by.email,
                                    game_report_comment.submitted_by.first_name,
                                    game_report_comment.submitted_by.last_name,
                                    game_report_comment.spirit,
                                    game_report_comment.comment.encode(
                                        "ascii", "ignore"
                                    ),
                                ]
                            )

                    return response

            else:
                games = league.game_set.order_by(
                    "date", "start", "field_name", "field_name__field"
                )
                game_locations = league.get_game_locations(games=games)
                game_dates = league.get_game_dates(
                    games=games, game_locations=game_locations
                )

                team_data = {}
                for team in league.team_set.all():
                    team_data.update(
                        {
                            team.id: {
                                "female_count": team.get_female_members_count(),
                                "male_count": team.get_male_members_count(),
                                "player_count": team.get_members_count(),
                                "attendance_values_female": [],
                                "attendance_values_male": [],
                                "attendance_values_player": [],
                                "spirit_values": [],
                            },
                        }
                    )

                for game_report in game_reports:
                    team_data[game_report.team.id]["attendance_values_player"].append(
                        game_report.num_players_in_attendance
                    )
                    team_data[game_report.team.id]["attendance_values_female"].append(
                        game_report.num_females_in_attendance
                    )
                    team_data[game_report.team.id]["attendance_values_male"].append(
                        game_report.num_males_in_attendance
                    )

                    for game_report_comment in game_report.gamereportcomment_set.all():
                        team_data[
                            game_report.game.get_opposing_team(game_report.team).id
                        ]["spirit_values"].append(game_report_comment.spirit)

    else:
        leagues = League.objects.all().order_by("-league_start_date")

    return render(
        request,
        "junta/gamereports.html",
        {
            "leagues": leagues,
            "league": league,
            "game": game,
            "team": team,
            "game_reports": game_reports,
            "game_locations": game_locations,
            "game_dates": game_dates,
            "team_data": team_data,
        },
    )


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name="junta").exists())
def registrationexport(request, year=None, season=None, division=None):
    leagues = League.objects.all().order_by("-league_start_date")

    if request.method == "POST":
        export_type = None
        report_format = request.POST.get("report_format")

        registrations = None

        response = HttpResponse(content_type="text/csv")
        writer = csv.writer(response)

        if "export_league" in request.POST:
            export_type = "league"

            try:
                league_id = int(request.POST.get("league_id", 0))
                league = get_object_or_404(League, id=league_id)

                if not report_format in ["admin", "captain"]:
                    raise Exception("bad report format")
            except:
                messages.error(
                    request, "You must specify a valid division and format to export."
                )
                return render(
                    request, "junta/registrationexport.html", {"leagues": leagues}
                )

            response["Content-Disposition"] = (
                'attachment; filename="a2u_{}.csv"'.format(league)
            )

            registrations = Registrations.objects.filter(
                Q(payment_complete=True)
                | Q(check_complete=True)
                | Q(paypal_complete=True)
            )

            if league_id:
                registrations = registrations.filter(league=league)

            registrations = registrations.extra(
                select={
                    "num_teams": "SELECT COUNT(team_member.id) FROM team_member WHERE team_member.user_id = registrations.user_id GROUP BY team_member.user_id"
                }
            )

        if "export_year" in request.POST:
            export_type = "year"

            try:
                year = int(request.POST.get("year", 0))

                if not year:
                    raise Exception("bad year")
            except:
                messages.error(request, "You must specify a valid year to export.")
                return render(
                    request, "junta/registrationexport.html", {"leagues": leagues}
                )

            response["Content-Disposition"] = (
                'attachment; filename="a2u_{}.csv"'.format(year)
            )

            registrations = Registrations.objects.filter(
                Q(payment_complete=True)
                | Q(check_complete=True)
                | Q(paypal_complete=True)
            )

            if year:
                registrations = registrations.filter(league__year=year)

        writer.writerow(get_export_headers(export_type, report_format))

        registration_list = []
        for registration in registrations:
            if registration.is_complete and not registration.refunded:
                paypal_row = PayPalIPN.objects.filter(
                    invoice=registration.paypal_invoice_id
                ).first()

                team_member_captain = all(
                    team_member.captain
                    for team_member in TeamMember.objects.filter(
                        user=registration.user,
                        team__league=registration.league,
                    )
                )

                try:
                    profile = reduce(getattr, "user.profile".split("."), registration)
                    matching_preference = profile.matching_preference
                    age_on_start_date = profile.get_age_on(
                        registration.league.league_start_date
                    )
                except AttributeError:
                    matching_preference = None
                    age_on_start_date = 0

                registration_data = {
                    "team_id": ",".join(str(id) for id in registration.get_team_ids()),
                    "is_captain": int(team_member_captain),
                    "first_name": registration.user.first_name,
                    "last_name": registration.user.last_name,
                    "email": registration.user.email,
                    "gender": matching_preference,
                    "age": int(0 if age_on_start_date is None else age_on_start_date),
                    "registration_status": registration.status,
                    "registration_timestamp": registration.registered,
                    "registration_waitlisted": int(registration.waitlist),
                    "registration_refunded": int(registration.refunded),
                    "payment_type": registration.pay_type,
                    "paypal_email": (
                        paypal_row.payer_email.encode("ascii", "ignore")
                        if paypal_row
                        else ""
                    ),
                    "paypal_amount": paypal_row.mc_gross if paypal_row else "",
                    "attendance": int(
                        0
                        if registration.attendance is None
                        else registration.attendance
                    ),
                    "captaining": int(
                        0 if registration.captain is None else registration.captain
                    ),
                }

                if export_type == "league":
                    try:
                        profile = reduce(
                            getattr, "user.profile".split("."), registration
                        )
                        height_inches = profile.height_inches
                        guardian_name = profile.guardian_name
                        guardian_email = profile.guardian_email
                        guardian_phone = profile.guardian_phone
                        prompt_response = getattr(
                            registration, "prompt_response", ""
                        ).encode("ascii", "ignore")
                    except AttributeError:
                        height_inches = 0
                        guardian_name = None
                        guardian_email = None
                        guardian_phone = None
                        prompt_response = None

                    rating_totals = registration.user.rating_totals

                    registration_data["baggage_id"] = registration.baggage.id
                    registration_data["baggage_size"] = int(registration.baggage_size)
                    registration_data["rating_total"] = rating_totals["total"]
                    registration_data["rating_experience"] = rating_totals["experience"]
                    registration_data["rating_strategy"] = rating_totals["strategy"]
                    registration_data["rating_throwing"] = rating_totals["throwing"]
                    registration_data["rating_athleticism"] = rating_totals[
                        "athleticism"
                    ]
                    registration_data["rating_competitiveness"] = (
                        registration.user.self_rating.competitiveness
                    )
                    registration_data["rating_spirit"] = rating_totals["spirit"]
                    registration_data["num_teams"] = registration.num_teams
                    registration_data["height"] = height_inches
                    registration_data["guardian_name"] = guardian_name
                    registration_data["guardian_email"] = guardian_email
                    registration_data["guardian_phone"] = guardian_phone
                    registration_data["prompt_response"] = prompt_response

                if export_type == "year":
                    registration_data["league"] = registration.league

                registration_list.append(registration_data)

        registration_list.sort(key=lambda k: k["last_name"].lower())
        registration_list.sort(key=lambda k: k["is_captain"], reverse=True)
        registration_list.sort(
            key=lambda k: "9999" if not k["team_id"] else k["team_id"]
        )

        for registration in registration_list:
            writer.writerow(get_export_values(export_type, report_format, registration))

        return response

    return render(request, "junta/registrationexport.html", {"leagues": leagues})


@login_required
@atomic
@user_passes_test(lambda u: u.is_superuser)
def teamgeneration(request, year=None, season=None, division=None):
    if year and season and division:
        league = get_object_or_404(
            League,
            Q(year=year),
            Q(season__name=season) | Q(season__slug=season),
            Q(night=division) | Q(night_slug=division),
        )
        teams = Team.objects.filter(league=league)
        players = []

        for registration in league.get_complete_registrations():
            rating_totals = registration.user.rating_totals
            players.append(
                {
                    "baggage": registration.baggage,
                    "baggage_id": registration.baggage.id,
                    "rating_totals": rating_totals,
                    "rating_total": rating_totals["total"],
                    "team_id": registration.get_team_ids().first(),
                    "user": registration.user,
                }
            )

        if request.method == "POST":

            def save_teams(teams_list):
                for team_object in teams_list:
                    team = None
                    if team_object["team_id"]:
                        team = Team.objects.get(id=team_object["team_id"])
                    else:
                        team = Team()
                        team.league = league
                        team.hidden = True
                        team.save()

                    if team:
                        for user in team_object["users"]:
                            try:
                                team_member = TeamMember.objects.get(
                                    team__league=league, user=user
                                )
                            except TeamMember.DoesNotExist:
                                team_member = TeamMember()
                                team_member.user = user

                            team_member.captain = user in team_object["captains"]
                            team_member.team = team
                            team_member.save()

            players.sort(key=lambda k: (k["team_id"], k["baggage_id"]))

            new_teams = []
            if "generate_teams" in request.POST:
                num_teams = int(request.POST.get("num_teams", 0))

                if not num_teams:
                    messages.error(
                        request, "You must specify a number of teams greater than zero."
                    )
                    return HttpResponseRedirect(
                        reverse(
                            "teamgeneration_league",
                            kwargs={
                                "year": year,
                                "season": season,
                                "division": division,
                            },
                        )
                    )

                if teams:
                    messages.error(
                        request,
                        "Teams were not generated. Teams already exist for this league.",
                    )
                    return HttpResponseRedirect(
                        reverse(
                            "teamgeneration_league",
                            kwargs={
                                "year": year,
                                "season": season,
                                "division": division,
                            },
                        )
                    )

                captain_users = {}
                for key in request.POST:
                    if (
                        key.startswith("player_captain_")
                        and int(request.POST[key]) != 0
                    ):
                        captain_users[int(key.split("_").pop())] = int(
                            request.POST[key]
                        )

                captain_teams = list(set(captain_users.values()))
                for key in captain_users:
                    captain_users[key] = captain_teams.index(captain_users[key])

                groups = list(
                    {
                        "baggage_id": k,
                        "players": sorted(
                            list(v), key=lambda k: k["rating_total"], reverse=True
                        ),
                    }
                    for k, v in groupby(players, key=lambda k: k["baggage_id"])
                )

                for group in groups:
                    group["rating_total"] = 0
                    group["rating_total_female"] = 0
                    group["rating_total_male"] = 0

                    group["rating_average"] = 0
                    group["rating_average_female"] = 0
                    group["rating_average_male"] = 0

                    group["num_players"] = len(group["players"])
                    group["num_females"] = 0
                    group["num_males"] = 0

                    group["captain"] = None

                    for player in group["players"]:
                        if player["user"].id in [key for key in captain_users]:
                            group["captain"] = captain_users[player["user"].id]

                        group["rating_total"] += float(player["rating_total"])

                        try:
                            if player["user"].profile.gender == "F":
                                group["num_females"] += 1
                                group["rating_total_female"] += float(
                                    player["rating_total"]
                                )
                            else:
                                group["num_males"] += 1
                                group["rating_total_male"] += float(
                                    player["rating_total"]
                                )
                        except Player.DoesNotExist:
                            group["num_males"] += 1
                            group["rating_total_male"] += float(player["rating_total"])

                    group["rating_average"] = (
                        group["rating_total"] / group["num_players"]
                    )
                    if group["num_females"]:
                        group["rating_average_female"] = (
                            group["rating_total_female"] / group["num_females"]
                        )
                    if group["num_males"]:
                        group["rating_average_male"] = (
                            group["rating_total_male"] / group["num_males"]
                        )

                captain_groups = [g for g in groups if not g["captain"] is None]
                female_groups = [
                    g for g in groups if g["num_females"] > 0 and g["captain"] is None
                ]
                male_groups = [
                    g for g in groups if g["num_females"] <= 0 and g["captain"] is None
                ]

                # sort female and male groups, least important to most important values
                # sort by average rating of group, low to high
                female_groups.sort(key=lambda k: k["rating_average_female"])
                male_groups.sort(key=lambda k: k["rating_average"])
                # sort by size of group, hight to low
                female_groups.sort(key=lambda k: k["num_players"], reverse=True)
                male_groups.sort(key=lambda k: k["num_players"], reverse=True)
                # sort female groups by number of females, high to low
                female_groups.sort(key=lambda k: k["num_females"], reverse=True)

                # create a team object to track the teams as they are built
                teams_object = list(
                    copy.deepcopy(
                        {
                            "num_players": 0,
                            "num_females": 0,
                            "num_males": 0,
                            "rating_total": 0.0,
                            "rating_total_female": 0.0,
                            "rating_total_male": 0.0,
                            "rating_average": 0.0,
                            "rating_average_female": 0.0,
                            "rating_average_male": 0.0,
                            "groups": [],
                            "players": [],
                        }
                    )
                    for i in range(num_teams)
                )

                # number of players on the biggest team
                team_cap = floor(float(len(players)) / num_teams)
                team_cap_female = floor(
                    float(len([p for p in players if p["user"].profile.gender == "F"]))
                    / num_teams
                )
                team_cap_male = floor(
                    float(len([p for p in players if p["user"].profile.gender == "M"]))
                    / num_teams
                )

                # add a group to a team and update all team values
                def assign_group_to_team(group, team):
                    team["groups"].append(group)
                    team["players"].extend(group["players"])

                    team["num_players"] += len(group["players"])
                    team["num_females"] += group["num_females"]
                    team["num_males"] += group["num_males"]

                    team["rating_total"] += group["rating_total"]
                    team["rating_total_female"] += group["rating_total_female"]
                    team["rating_total_male"] += group["rating_total_male"]

                    team["rating_average"] = team["rating_total"] / team["num_players"]
                    if team["num_females"]:
                        team["rating_average_female"] = (
                            team["rating_total_female"] / team["num_females"]
                        )
                    if team["num_males"]:
                        team["rating_average_male"] = (
                            team["rating_total_male"] / team["num_males"]
                        )

                def debug_group(group):
                    print(
                        (
                            "\n\nPLACING GROUP: {} players, {} average rating".format(
                                group["num_players"], group["rating_average"]
                            )
                        )
                    )
                    print("PLAYERS")
                    for player in group["players"]:
                        print((player["user"]))

                def debug_teams(teams):
                    print("TEAMS")
                    print("=====")
                    for team in teams:
                        print(
                            (
                                "{} players, {} females, {} average rating, {} average female rating, {}".format(
                                    team["num_players"],
                                    team["num_females"],
                                    team["rating_average"],
                                    team["rating_average_female"],
                                    (
                                        team["players"][0]["user"]
                                        if len(team["players"])
                                        else None
                                    ),
                                )
                            )
                        )

                # distribute the groups with captains in them, one per team
                for group in captain_groups:
                    # debug_group(group)

                    if not group["captain"] is None and group["captain"] < num_teams:
                        assign_group_to_team(group, teams_object[group["captain"]])
                        # debug_teams(teams_object)

                # distribute the groups with females in them, should split females as evenly as possible
                for group in female_groups:
                    # debug_group(group)

                    teams_object.sort(
                        key=lambda k: k["rating_average_female"], reverse=True
                    )
                    # teams_object.sort(key=lambda k: k['num_females'])
                    teams_object.sort(key=lambda k: k["num_players"])
                    teams_object.sort(
                        key=lambda k: (
                            0
                            if (k["num_females"] + group["num_females"])
                            <= team_cap_female
                            else k["num_females"]
                            + group["num_females"]
                            - team_cap_female
                        )
                    )

                    if (
                        group["rating_average_female"]
                        > teams_object[0]["rating_average_female"]
                    ):
                        teams_object.sort(key=lambda k: k["rating_average_female"])
                        # teams_object.sort(key=lambda k: k['num_females'])
                        teams_object.sort(key=lambda k: k["num_players"])
                        teams_object.sort(
                            key=lambda k: (
                                0
                                if (k["num_females"] + group["num_females"])
                                <= team_cap_female
                                else k["num_females"]
                                + group["num_females"]
                                - team_cap_female
                            )
                        )

                    assign_group_to_team(group, teams_object[0])
                    # debug_teams(teams_object)

                # distribute the remaining groups (all male groups)
                for group in male_groups:
                    # debug_group(group)

                    teams_object.sort(key=lambda k: k["rating_average"], reverse=True)
                    teams_object.sort(key=lambda k: k["num_players"])
                    teams_object.sort(
                        key=lambda k: (
                            0
                            if (k["num_players"] + group["num_players"]) <= team_cap
                            else k["num_players"] + group["num_players"] - team_cap
                        )
                    )

                    if group["rating_average"] > teams_object[0]["rating_average"]:
                        teams_object.sort(key=lambda k: k["rating_average"])
                        teams_object.sort(key=lambda k: k["num_players"])
                        teams_object.sort(
                            key=lambda k: (
                                0
                                if (k["num_players"] + group["num_players"]) <= team_cap
                                else k["num_players"] + group["num_players"] - team_cap
                            )
                        )

                    assign_group_to_team(group, teams_object[0])
                    # debug_teams(teams_object)

                # reorganize new teams so that they can be saved
                for team in teams_object:
                    new_teams.append(
                        {
                            "captains": list(
                                get_user_model().objects.get(id=user_id)
                                for user_id in list(captain_users.keys())
                            ),
                            "team_id": None,
                            "users": [player["user"] for player in team["players"]],
                        }
                    )
            elif "save_teams" in request.POST:
                for key in request.POST:
                    team_member_match = re.match(r"^team_member_([\d]+)$", key)
                    team_member_captain_match = re.match(
                        r"^team_member_captain_([\d]+)$", key
                    )

                    if team_member_match:
                        team_id = int(team_member_match.group(1))
                        if team_id:
                            team = [
                                team for team in new_teams if team["team_id"] == team_id
                            ]

                            users = list(
                                get_user_model().objects.get(id=user_id)
                                for user_id in request.POST.getlist(key)
                            )

                            if team:
                                team[0]["users"] = users
                            else:
                                new_teams.append(
                                    {"captains": [], "team_id": team_id, "users": users}
                                )

                    elif team_member_captain_match:
                        team_id = int(team_member_captain_match.group(1))
                        if team_id:
                            team = [
                                team for team in new_teams if team["team_id"] == team_id
                            ]

                            captains = list(
                                get_user_model().objects.get(id=user_id)
                                for user_id in request.POST.getlist(key)
                            )

                            if team:
                                team[0]["captains"] = captains
                            else:
                                new_teams.append(
                                    {
                                        "captains": captains,
                                        "team_id": team_id,
                                        "users": [],
                                    }
                                )

                save_teams(new_teams)

                messages.success(request, "Teams were successfully saved.")
                return HttpResponseRedirect(
                    reverse(
                        "teamgeneration_league",
                        kwargs={"year": year, "season": season, "division": division},
                    )
                )

            if "publish_teams" in request.POST:
                teams.update(hidden=False)

                messages.success(request, "Teams were successfully published.")
                return HttpResponseRedirect(
                    reverse(
                        "teamgeneration_league",
                        kwargs={"year": year, "season": season, "division": division},
                    )
                )

            elif "hide_teams" in request.POST:
                teams.update(hidden=True)

                messages.success(request, "Teams were successfully hidden.")
                return HttpResponseRedirect(
                    reverse(
                        "teamgeneration_league",
                        kwargs={"year": year, "season": season, "division": division},
                    )
                )
            elif "delete_teams" in request.POST:
                teams.delete()

                messages.success(request, "Teams were successfully deleted.")
                return HttpResponseRedirect(
                    reverse(
                        "teamgeneration_league",
                        kwargs={"year": year, "season": season, "division": division},
                    )
                )
            # if POST and no other parameter, need to save newly generated teams
            else:
                save_teams(new_teams)

                messages.success(request, "Teams were successfully generated.")
                return HttpResponseRedirect(
                    reverse(
                        "teamgeneration_league",
                        kwargs={"year": year, "season": season, "division": division},
                    )
                )

        players.sort(key=lambda k: (k["rating_total"]), reverse=True)

        response_dictionary = {
            "league": league,
            "teams": teams,
            "players": players,
            "unassigned_registrations": league.get_unassigned_registrations(),
        }

    else:
        leagues = League.objects.all().order_by("-league_start_date")
        response_dictionary = {"leagues": leagues}

    return render(request, "junta/teamgeneration.html", response_dictionary)


@login_required
@atomic
@user_passes_test(lambda u: u.is_superuser)
def schedulegeneration(request, year=None, season=None, division=None):
    leagues = None
    league = None
    games = None
    game_locations = None
    game_dates = None

    form = None
    schedule = None
    num_necessary_fields = 0

    if year and season and division:
        league = get_object_or_404(
            League,
            Q(year=year),
            Q(season__name=season) | Q(season__slug=season),
            Q(night=division) | Q(night_slug=division),
        )
        games = league.game_set.order_by(
            "date", "start", "field_name", "field_name__field"
        )
        game_locations = league.get_game_locations(games=games)
        game_dates = league.get_game_dates(games=games, game_locations=game_locations)

        num_events = league.get_num_game_events()

        schedule = []
        teams = list(Team.objects.filter(league=league))
        num_teams = len(teams)

        if teams and num_teams >= 2:
            teams = teams[0::2] + list(reversed(teams[1::2]))
            teams = teams[:1] + teams[2:] + teams[1:2]

            for event_num in range(0, num_events):
                teams = teams[:1] + teams[-1:] + teams[1:-1]

                top = teams[: num_teams // 2]
                bottom = list(reversed(teams[num_teams // 2 :]))
                games = list(zip(top, bottom))

                num_slots = num_teams // 2
                num_unique_games = num_teams - 1

                shift = (event_num // num_unique_games) + ((event_num * 2) % num_slots)
                games = games[-shift:] + games[:-shift]

                schedule_teams = [
                    team for game in games for team in sorted(game, key=lambda k: k.id)
                ]
                schedule.append(schedule_teams)

        num_necessary_fields = int(ceil(1.0 * num_teams / 2 / league.num_time_slots))

        if request.method == "POST":
            if "generate_schedule" in request.POST:
                form = ScheduleGenerationForm(request.POST)
                field_names = request.POST.getlist("field_names")
                num_field_names = len(field_names)

                if form.is_valid() and num_field_names >= num_necessary_fields:
                    start_datetime = datetime.combine(datetime.min, league.start_time)

                    if league.start_time <= league.end_time:
                        end_datetime = datetime.combine(datetime.min, league.end_time)
                    else:
                        end_datetime = datetime.combine(
                            datetime.min + timedelta(days=1), league.end_time
                        )

                    time_delta = end_datetime - start_datetime
                    time_slot_delta = time_delta / league.num_time_slots

                    event_date = league.league_start_date
                    field_names = FieldNames.objects.filter(pk__in=field_names)

                    for event in schedule:
                        event_datetime = datetime.combine(event_date, league.start_time)

                        for i, team in enumerate(event):
                            if i % 2 == 0:
                                game = Game()
                                game.date = event_date
                                game.start = event_datetime
                                game.field_name = field_names[
                                    int(i / 2) % num_field_names
                                ]
                                game.league = league
                                game.save()

                            game_team = GameTeams()
                            game_team.game = game
                            game_team.team = team
                            game_team.save()

                            # if no new game/will create new game on next loop
                            if not i % 2 == 0:
                                # if out of fields for timeslot
                                if int((i / 2) + 1) % num_field_names == 0:
                                    event_datetime += time_slot_delta

                        event_date = event_date + timedelta(days=7)

                    messages.success(request, "Schedule was successfully generated.")
                    return HttpResponseRedirect(
                        reverse(
                            "schedulegeneration_league",
                            kwargs={
                                "year": year,
                                "season": season,
                                "division": division,
                            },
                        )
                    )
                else:
                    if num_field_names >= num_necessary_fields:
                        messages.error(
                            request, "There was an issue with the form you submitted."
                        )
                    else:
                        messages.error(
                            request,
                            "You must pick enough fields to cover the number of games for an event.",
                        )
            elif "clear_schedule" in request.POST:
                Game.objects.filter(league=league).delete()

                messages.success(request, "Schedule was successfully cleared.")
                return HttpResponseRedirect(
                    reverse(
                        "schedulegeneration_league",
                        kwargs={"year": year, "season": season, "division": division},
                    )
                )
        else:
            form = ScheduleGenerationForm()

        form.fields["field_names"].queryset = FieldNames.objects.filter(
            field__league=league, hidden=False
        )

    else:
        leagues = League.objects.all().order_by("-league_start_date")

    return render(
        request,
        "junta/schedulegeneration.html",
        {
            "leagues": leagues,
            "league": league,
            "game_locations": game_locations,
            "game_dates": game_dates,
            "form": form,
            "schedule": schedule,
            "num_necessary_fields": num_necessary_fields,
        },
    )
