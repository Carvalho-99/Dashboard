import calendar


class SmartPlanner:
    """
    Algoritmo inteligente de planejamento financeiro.

    Lógica:
    - Cria janelas de pagamento com base nas datas de recebimento
    - Cada janela vai do dia do recebimento até o dia antes do próximo
    - Conta é atribuída à janela cujo recebimento chega ANTES do vencimento
    - Prioridade: Crítico > Importante > Normal > Opcional
    - Sempre mantém a reserva configurada
    - Contas críticas/importantes são pagas mesmo que fique abaixo da reserva

    Modo simulação:
    - deferred_ids: contas movidas para a próxima janela pelo usuário
    - next_month_ids: contas removidas deste mês (deixadas para o próximo)
    """

    def generate_plan(self, month, year, incomes, bills,
                      paid_ids=None, reserve=300, savings_goal=0,
                      deferred_ids=None, next_month_ids=None, advance_ids=None):
        if paid_ids is None:
            paid_ids = set()
        if deferred_ids is None:
            deferred_ids = set()
        if next_month_ids is None:
            next_month_ids = set()
        if advance_ids is None:
            advance_ids = set()

        if not incomes:
            return self._empty_plan(bills, paid_ids)

        incomes_sorted = sorted(incomes, key=lambda x: x['day_of_month'])
        bills_sorted   = sorted(bills,   key=lambda x: (x['priority'], x['due_day']))
        last_day       = calendar.monthrange(year, month)[1]

        active_bills = [b for b in bills if b['id'] not in next_month_ids]
        total_income = sum(i['amount'] for i in incomes)
        total_bills  = sum(b['amount'] for b in active_bills)
        paid_bills   = [b for b in bills if b['id'] in paid_ids]
        unpaid_bills = [b for b in bills_sorted
                        if b['id'] not in paid_ids and b['id'] not in next_month_ids]
        total_paid   = sum(b['amount'] for b in paid_bills)

        # ---- Criar janelas ----
        windows = []
        for i, income in enumerate(incomes_sorted):
            if i + 1 < len(incomes_sorted):
                win_end = incomes_sorted[i + 1]['day_of_month'] - 1
            else:
                win_end = last_day
            windows.append({
                'income':      income,
                'income_day':  income['day_of_month'],
                'win_end':     win_end,
                'bills':       [],
                'freed_bills': [],  # contas removidas desta janela pelo usuário
            })

        first_income_day = incomes_sorted[0]['day_of_month']
        early_bills  = []
        unfit_bills  = []

        for bill in unpaid_bills:
            is_deferred = bill['id'] in deferred_ids

            # Encontra janela natural
            natural_idx = None
            if bill['due_day'] >= first_income_day:
                for i, window in enumerate(reversed(windows)):
                    if window['income_day'] <= bill['due_day']:
                        natural_idx = len(windows) - 1 - i
                        break

            if is_deferred:
                if natural_idx is not None:
                    windows[natural_idx]['freed_bills'].append(bill)
                    next_idx = natural_idx + 1
                else:
                    next_idx = 0

                if next_idx < len(windows):
                    windows[next_idx]['bills'].append(bill)
                # else: sem próxima janela → excluída (tratada como próximo mês)

            elif bill['id'] in advance_ids:
                # Adiantada: move para a janela anterior à natural
                if natural_idx is not None and natural_idx > 0:
                    windows[natural_idx - 1]['bills'].append(bill)
                elif natural_idx == 0:
                    windows[0]['bills'].append(bill)
                else:
                    windows[0]['bills'].append(bill)

            else:
                if natural_idx is not None:
                    windows[natural_idx]['bills'].append(bill)
                else:
                    early_bills.append(bill)

        # ---- Simular mês ----
        running_balance = 0
        warnings        = []
        steps           = []

        if early_bills:
            early_total = sum(b['amount'] for b in early_bills)
            warnings.append({
                'type':    'early',
                'level':   'warning',
                'message': (
                    f'{len(early_bills)} conta(s) vencem antes do primeiro recebimento '
                    f'(dia {first_income_day}). Reserve R$ {early_total:,.2f} do mês anterior.'
                ),
                'bills': early_bills,
            })

        for window in windows:
            income      = window['income']
            win_bills   = sorted(window['bills'], key=lambda x: (x['priority'], x['due_day']))
            freed_bills = window['freed_bills']
            balance_in  = running_balance + income['amount']
            running_balance = balance_in

            to_pay    = []
            to_defer  = []

            for bill in win_bills:
                if running_balance - bill['amount'] >= reserve:
                    to_pay.append(bill)
                    running_balance -= bill['amount']
                else:
                    if bill['priority'] <= 2:
                        to_pay.append(bill)
                        running_balance -= bill['amount']
                        warnings.append({
                            'type':    'low_reserve',
                            'level':   'warning',
                            'message': (
                                f'Pagar "{bill["name"]}" (R$ {bill["amount"]:,.2f}) deixa saldo '
                                f'abaixo da reserva de R$ {reserve:,.0f}.'
                            ),
                        })
                    else:
                        to_defer.append(bill)
                        warnings.append({
                            'type':    'deferred',
                            'level':   'danger',
                            'message': (
                                f'"{bill["name"]}" (R$ {bill["amount"]:,.2f}) foi adiada — '
                                f'saldo insuficiente mantendo reserva.'
                            ),
                        })

            if running_balance < 0:
                warnings.append({
                    'type':    'deficit',
                    'level':   'danger',
                    'message': (
                        f'Déficit após {income["name"]}! '
                        f'Saldo negativo de R$ {abs(running_balance):,.2f}.'
                    ),
                })

            urgency_map = self._build_urgency(win_bills, income['day_of_month'])

            steps.append({
                'income':          income,
                'bills_to_pay':    to_pay,
                'bills_deferred':  to_defer,
                'bills_total':     sum(b['amount'] for b in to_pay),
                'balance_before':  balance_in,
                'balance_after':   running_balance,
                'ok':              not to_defer and running_balance >= 0,
                'urgency':         urgency_map,
                'freed_bills':     freed_bills,
                'freed_total':     sum(b['amount'] for b in freed_bills),
            })

        if total_income < total_bills:
            diff = total_bills - total_income
            warnings.insert(0, {
                'type':    'total_deficit',
                'level':   'danger',
                'message': (
                    f'ATENÇÃO: Suas contas (R$ {total_bills:,.2f}) excedem sua renda '
                    f'(R$ {total_income:,.2f}) em R$ {diff:,.2f}.'
                ),
            })

        savings     = total_income - total_bills
        goal_status = None
        if savings_goal > 0:
            if savings >= savings_goal:
                goal_status = {'ok': True,  'diff': savings - savings_goal}
            else:
                goal_status = {'ok': False, 'diff': savings_goal - savings}

        tip = self._generate_tip(steps, total_income, total_bills, reserve, savings)

        next_month_bills = [b for b in bills
                            if b['id'] in next_month_ids and b['id'] not in paid_ids]

        return {
            'steps':            steps,
            'early_bills':      early_bills,
            'paid_bills':       paid_bills,
            'warnings':         warnings,
            'total_income':     total_income,
            'total_bills':      total_bills,
            'total_paid':       total_paid,
            'total_unpaid':     total_bills - total_paid,
            'savings':          savings,
            'savings_pct':      (savings / total_income * 100) if total_income > 0 else 0,
            'projected_left':   running_balance,
            'has_deficit':      total_income < total_bills,
            'reserve':          reserve,
            'savings_goal':     savings_goal,
            'goal_status':      goal_status,
            'tip':              tip,
            'next_month_bills': next_month_bills,
        }

    def _build_urgency(self, bills, income_day):
        urgency = {}
        for b in bills:
            days_after_income = b['due_day'] - income_day
            if days_after_income <= 3:
                urgency[b['id']] = 'danger'
            elif days_after_income <= 7:
                urgency[b['id']] = 'warning'
            else:
                urgency[b['id']] = 'normal'
        return urgency

    def _generate_tip(self, steps, total_income, total_bills, reserve, savings):
        if total_income == 0:
            return None

        pct = (savings / total_income) * 100

        if savings < 0:
            return {
                'icon':  'exclamation-triangle',
                'color': 'danger',
                'text':  (
                    'Suas contas superam sua renda. Considere cortar gastos opcionais '
                    'ou negociar valores de contas recorrentes.'
                ),
            }
        elif pct < 10:
            return {
                'icon':  'info-circle',
                'color': 'warning',
                'text':  (
                    f'Você economiza {pct:.1f}% da renda. O ideal é pelo menos 20%. '
                    'Analise contas opcionais que podem ser reduzidas.'
                ),
            }
        elif pct < 20:
            return {
                'icon':  'lightbulb',
                'color': 'info',
                'text':  (
                    f'Você economiza {pct:.1f}% da renda — bom! Tente chegar a 20% '
                    'para construir uma reserva de emergência mais sólida.'
                ),
            }
        else:
            return {
                'icon':  'check-circle',
                'color': 'success',
                'text':  (
                    f'Ótimo! Você economiza {pct:.1f}% da renda. '
                    'Considere investir o excedente para fazer o dinheiro trabalhar por você.'
                ),
            }

    def _empty_plan(self, bills, paid_ids):
        total_bills = sum(b['amount'] for b in bills)
        return {
            'steps':            [],
            'early_bills':      [],
            'paid_bills':       [],
            'warnings':         [{
                'type':    'no_income',
                'level':   'warning',
                'message': 'Nenhuma fonte de renda cadastrada. Adicione seu salário em "Rendas".',
            }],
            'total_income':     0,
            'total_bills':      total_bills,
            'total_paid':       0,
            'total_unpaid':     sum(b['amount'] for b in bills if b['id'] not in paid_ids),
            'savings':          -total_bills,
            'savings_pct':      0,
            'projected_left':   0,
            'has_deficit':      True,
            'reserve':          300,
            'savings_goal':     0,
            'goal_status':      None,
            'tip':              None,
            'next_month_bills': [],
        }
