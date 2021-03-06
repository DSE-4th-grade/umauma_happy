from django.shortcuts import render, get_object_or_404, get_list_or_404
from umauma_happy_app.models import *
from umauma_happy_app.utils import analysis
from collections import OrderedDict
import datetime
import time
import io, sys


class SampleValues:
    analysis_number_samples = [100, 200, 500, 1000, 2000, 5000]


class ScheduledSample:
    start_delta = 0
    end_delta = 1000


def index(request):
    """
    他者分析の分析内容の選択画面
    :param request: Request
    :return render: with Request request, Dictionary context
    """
    context = {'analysis_number_samples': SampleValues.analysis_number_samples,
               'weight_amount': len(analysis.get_weight())}
    return render(request, 'social_analysis/index.html', context)


def calculate(request, analysis_number=None):
    """
    他者分析の全ユーザー要素別的中率の表示
    :param request: Request
    :param analysis_number: int
    :return render: with Request request, Dictionary context
    """
    pre_time = time.time()  # 経過時間表示用
    weights = analysis.get_weight(analysis_number)
    factor_count = analysis.count_factor(weights)
    context = {'analysis_number_samples': SampleValues.analysis_number_samples,
               'factor_count': factor_count,
               'analysis_number': analysis_number,
               'calculation_duration': time.time() - pre_time}
    return render(request, 'social_analysis/calculate.html', context)


def calculate_by_period(request, start, end):
    """
    他者分析の全ユーザー該当期間の要素別的中率の表示
    :param request: Request
    :param start: String(YYYY-MM-DD HH:MM:ss)
    :param end: String(YYYY-MM-DD HH:MM:ss)
    :return render: with Request request, Dictionary context
    """
    pre_time = datetime.datetime.now()  # 経過時間表示用
    race_list = analysis.get_race_by_period(start, end)
    count_factor_by_races(race_list)
    context = {'analysis_number_samples': SampleValues.analysis_number_samples,
               'analysis_start': start,
               'analysis_end': end,
               'analysis_race_number': len(race_list),
               'calculation_duration': datetime.datetime.now() - pre_time}
    return render(request, 'social_analysis/calculate.html', context)


def calculate_remaining(request):
    """
    未処理のレースに対して,的中率を計算する
    :param request: Request
    :return factor_counter: Dictionary
    """
    pre_time = datetime.datetime.now()  # 経過時間表示用
    reservation_race_list = []
    race_list = Race.objects.all()
    for race in race_list:
        if is_calculated_factor_aggregate(race) is False:
            reservation_race_list.append(race)
    count_factor_by_races(reservation_race_list)
    context = {'analysis_number_samples': SampleValues.analysis_number_samples,
               'analysis_race_number': len(reservation_race_list),
               'calculation_duration': datetime.datetime.now() - pre_time}
    return render(request, 'social_analysis/calculate.html', context)


def show_all_aggregate(request):
    """
    計算済みの要素別的中率を要素別に表示(全期間)
    :param request:
    :return:
    """
    pre_time = time.time()  # 経過時間表示用
    summarize_past = summarize_past_race_aggregate()
    summarize_future = summarize_future_race_aggregate()

    context = {'analysis_number_samples': SampleValues.analysis_number_samples,
               'factor_count_past': summarize_past['factor_counter'],
               'factor_count_future': summarize_future['factor_counter'],
               'analysis_number_past': summarize_past['analysis_number'],
               'analysis_number_future': summarize_future['analysis_number'],
               'analysis_race_number_past': summarize_past['analysis_race_number'],
               'analysis_race_number_future': summarize_future['analysis_race_number'],
               'calculation_duration': time.time() - pre_time}
    return render(request, 'social_analysis/calculate.html', context)


def is_calculated_factor_aggregate(race, factor=None):
    """
    与えられたレースの全ユーザの使用率が計算済みか判定
    :param race: Object
    :return: boolean
    """
    if factor is None:
        analysis_data_list = list(EntireFactorAggregate.objects.filter(race_id=race.id))
        if len(analysis_data_list) == 0:
            return False
        else:
            return True
    else:
        analysis_data_list = list(EntireFactorAggregate.objects.filter(race_id=race.id, factor_id=factor.id))
        if len(analysis_data_list) == 0:
            return False
        else:
            return True


def save(factor_count, race):
    """
    全ユーザーの要素別使用回数,的中回数,的中率をレース毎にDBに保存
    :param factor_count: Dictionary
    :param race: String or Datetime
    :return:
    """
    for key, value in factor_count.items():
        if is_calculated_factor_aggregate(race, key):
            analysis_data_list = list(EntireFactorAggregate.objects.filter(factor_id=key.id, race_id=race.id))
            analysis_data = analysis_data_list[0]
        else:
            analysis_data = EntireFactorAggregate()
        if value.keys() >= {'hit', 'hit_percentage'}:  # hit,hit_percentageが格納されている時
            analysis_data.hit = value['hit']
            analysis_data.hit_percentage = value['hit_percentage']
        analysis_data.use = value['use']
        analysis_data.use_percentage = value['use_percentage']
        analysis_data.factor_id = key.id
        analysis_data.race_id = race.id
        analysis_data.save()
    print(f'{datetime.datetime.now()} | Complete saving {len(factor_count)} data in EntireFactorAggregate.')
    return


def count_factor_by_races(race_list):
    """
    与えられたRaceリストを指定しているweightの的中率等を計算し, レース毎にDBに保存
    :param race_list: List
    :return factor_counter: Dictionary
    """
    for race in race_list:
        weights = analysis.get_weight_by_race(race)
        if analysis.is_not_null_rank_in_data(race):
            factor_counter = analysis.count_factor(weights)
        else:
            factor_counter = analysis.count_factor_only_use(weights)
        save(factor_counter, race)
    return


def summarize_past_race_aggregate():
    """
    EntireFactorAggregateの過去レースに関して,的中率、使用率、使用回数、的中回数を集計する
    :return compact: Dictionary
    """
    factor_list_all = list(Factor.objects.all())
    factor_counter_past = analysis.init_factor_counter()
    analysis_number_past = 0
    # 過去レースに関する計算結果を取得
    analysis_data_list_past = list(EntireFactorAggregate.objects.filter(hit__isnull=False))
    for analysis_data in analysis_data_list_past:
        factor_counter_past[analysis_data.factor]['use'] += analysis_data.use
        factor_counter_past[analysis_data.factor]['hit'] += analysis_data.hit
        analysis_number_past += analysis_data.use
    # 的中率と使用率を計算
    factor_counter_past = analysis.calculate_use_percentage(factor_counter_past, factor_list_all)
    factor_counter_past = analysis.calculate_hit_percentage(factor_counter_past, factor_list_all)
    compact = {'factor_counter': factor_counter_past,
               'analysis_number': analysis_number_past,
               'analysis_race_number': int(len(analysis_data_list_past) / len(factor_list_all))}
    return compact


def summarize_future_race_aggregate():
    """
    EntireFactorAggregateの過去レースに関して,使用率、使用回数、を集計する
    :return compact: Dictionary
    """
    factor_list_all = list(Factor.objects.all())
    factor_counter_future = analysis.init_factor_counter_only_use()
    analysis_number_future = 0
    # 未来レースに関する計算結果を取得
    analysis_data_list_future = list(EntireFactorAggregate.objects.filter(hit__isnull=True))
    for analysis_data in analysis_data_list_future:
        factor_counter_future[analysis_data.factor]['use'] += analysis_data.use
        analysis_number_future += analysis_data.use
    # 使用率を計算
    factor_counter_future = analysis.calculate_use_percentage(factor_counter_future, factor_list_all)
    compact = {'factor_counter': factor_counter_future,
               'analysis_number': analysis_number_future,
               'analysis_race_number': int(len(analysis_data_list_future) / len(factor_list_all))}
    return compact


def scheduled_calculate():
    """
    バッチ処理の内容[未来のレースについて毎日使用率を計算する]
    'python manage.py crontab add'を実行すると setting.py で設定した間隔で実行される
    'python manage.py crontab remove'を実行するとバッチが全解除される
    'python manage.py crontab show'を実行すると登録されているバッチが確認できる
    :return:
    """
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')  # ログ出力の文字コードをセット
    pre_time = time.time()
    today = datetime.date.today()
    start_time = today + datetime.timedelta(days=ScheduledSample.start_delta)
    end_time = today + datetime.timedelta(days=ScheduledSample.end_delta)
    race_list = analysis.get_race_by_period(start_time, end_time)
    print(f'{datetime.datetime.now()} | Start calculate {len(race_list)}Races in {start_time} ~ {end_time}')
    count_factor_by_races(race_list)
    print(f'{datetime.datetime.now()} | Complete calculate {len(race_list)}Races in {start_time} ~ {end_time}'
          f'Run Time : {time.time() - pre_time:.5}s')
