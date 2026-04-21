from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import random
import os
from datetime import datetime, timedelta
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'rpg_heart_of_elidor_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(os.path.dirname(__file__), "rpg.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация с async_mode='threading' для совместимости
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

# === Модели ===

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    is_online = db.Column(db.Boolean, default=False)
    
    player = db.relationship('Player', backref='user', uselist=False)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    level = db.Column(db.Integer, default=1)
    exp = db.Column(db.Integer, default=0)
    next_exp = db.Column(db.Integer, default=100)
    hp = db.Column(db.Integer, default=120)
    max_hp = db.Column(db.Integer, default=120)
    stamina = db.Column(db.Integer, default=100)
    max_stamina = db.Column(db.Integer, default=100)
    attack = db.Column(db.Integer, default=20)
    defense = db.Column(db.Integer, default=8)
    crit_chance = db.Column(db.Integer, default=10)
    crit_damage = db.Column(db.Integer, default=150)
    dodge_chance = db.Column(db.Integer, default=8)
    gold = db.Column(db.Integer, default=100)
    current_location = db.Column(db.String(20), default="деревня")
    inventory = db.Column(db.String(2000), default="Зелье здоровья x3,Зелье энергии x2")
    monsters_killed = db.Column(db.Integer, default=0)
    skill_points = db.Column(db.Integer, default=3)
    
    # Навыки
    skill_strength = db.Column(db.Integer, default=0)
    skill_agility = db.Column(db.Integer, default=0)
    skill_vitality = db.Column(db.Integer, default=0)
    skill_intellect = db.Column(db.Integer, default=0)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'level': self.level,
            'exp': self.exp,
            'next_exp': self.next_exp,
            'hp': self.hp,
            'max_hp': self.max_hp,
            'stamina': self.stamina,
            'max_stamina': self.max_stamina,
            'attack': self.attack,
            'defense': self.defense,
            'crit_chance': self.crit_chance,
            'crit_damage': self.crit_damage,
            'dodge_chance': self.dodge_chance,
            'gold': self.gold,
            'current_location': self.current_location,
            'inventory': self.inventory.split(",") if self.inventory else [],
            'monsters_killed': self.monsters_killed,
            'skill_points': self.skill_points,
            'skills': {
                'strength': self.skill_strength,
                'agility': self.skill_agility,
                'vitality': self.skill_vitality,
                'intellect': self.skill_intellect
            }
        }
    
    def apply_skill_bonuses(self):
        self.attack = 20 + (self.skill_strength * 3)
        self.defense = 8 + (self.skill_vitality * 2)
        self.crit_chance = 10 + (self.skill_agility * 2)
        self.max_hp = 120 + (self.skill_vitality * 15)
        self.max_stamina = 100 + (self.skill_intellect * 5)
        if self.hp > self.max_hp:
            self.hp = self.max_hp
        if self.stamina > self.max_stamina:
            self.stamina = self.max_stamina

# === Мобы с балансом ===
MOBS = {
    "деревня": [
        {"name": "Бродячий пёс", "hp": 45, "max_hp": 45, "exp": 25, "gold": 15, "attack": 12, "defense": 3, "level": 1},
        {"name": "Лесная крыса", "hp": 35, "max_hp": 35, "exp": 20, "gold": 10, "attack": 10, "defense": 2, "level": 1}
    ],
    "лес": [
        {"name": "Лесной Волк", "hp": 75, "max_hp": 75, "exp": 45, "gold": 30, "attack": 18, "defense": 5, "level": 3},
        {"name": "Дикий кабан", "hp": 90, "max_hp": 90, "exp": 55, "gold": 35, "attack": 20, "defense": 7, "level": 4},
        {"name": "Лесной дух", "hp": 60, "max_hp": 60, "exp": 40, "gold": 25, "attack": 22, "defense": 4, "level": 3}
    ],
    "пещера": [
        {"name": "Гоблин-шаман", "hp": 110, "max_hp": 110, "exp": 70, "gold": 50, "attack": 25, "defense": 8, "level": 6},
        {"name": "Каменный голем", "hp": 150, "max_hp": 150, "exp": 90, "gold": 60, "attack": 28, "defense": 15, "level": 7},
        {"name": "Тёмный эльф", "hp": 95, "max_hp": 95, "exp": 65, "gold": 45, "attack": 30, "defense": 6, "level": 6}
    ],
    "арена": [
        {"name": "Гладиатор", "hp": 180, "max_hp": 180, "exp": 120, "gold": 80, "attack": 35, "defense": 12, "level": 10},
        {"name": "Паладин", "hp": 200, "max_hp": 200, "exp": 150, "gold": 100, "attack": 32, "defense": 18, "level": 12},
        {"name": "Мастер меча", "hp": 160, "max_hp": 160, "exp": 130, "gold": 90, "attack": 40, "defense": 10, "level": 11}
    ]
}

# Хранилище боев
battles = {}

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# === Маршруты ===

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login')
def login_page():
    if current_user.is_authenticated:
        return redirect('/')
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        login_user(user)
        user.is_online = True
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Неверные данные'}), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Пользователь существует'}), 400
    
    player = Player(name=username)
    db.session.add(player)
    db.session.flush()
    
    user = User(username=username)
    user.set_password(password)
    user.player_id = player.id
    db.session.add(user)
    db.session.commit()
    
    login_user(user)
    user.is_online = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/logout')
@login_required
def logout():
    current_user.is_online = False
    db.session.commit()
    logout_user()
    return jsonify({'success': True})

@app.route('/api/leaderboard')
def leaderboard():
    players = Player.query.order_by(Player.level.desc(), Player.exp.desc()).limit(10).all()
    return jsonify([{'name': p.name, 'level': p.level, 'kills': p.monsters_killed} for p in players])

@app.route('/api/upgrade_skill', methods=['POST'])
@login_required
def upgrade_skill():
    data = request.json
    skill = data.get('skill')
    player = current_user.player
    
    if player.skill_points <= 0:
        return jsonify({'error': 'Нет очков навыков!'}), 400
    
    if skill == 'strength':
        player.skill_strength += 1
        player.attack += 3
    elif skill == 'agility':
        player.skill_agility += 1
        player.crit_chance += 2
    elif skill == 'vitality':
        player.skill_vitality += 1
        player.max_hp += 15
        player.hp += 15
        player.defense += 2
    elif skill == 'intellect':
        player.skill_intellect += 1
        player.max_stamina += 5
        player.stamina += 5
    else:
        return jsonify({'error': 'Неверный навык!'}), 400
    
    player.skill_points -= 1
    player.apply_skill_bonuses()
    db.session.commit()
    
    return jsonify({'success': True, 'player': player.to_dict()})

# === Socket.IO события ===

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        player = current_user.player
        player.apply_skill_bonuses()
        db.session.commit()
        join_room('global')
        join_room(player.current_location)
        emit('player_data', player.to_dict())
        print(f"✅ {player.name} подключился")

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        player = current_user.player
        current_user.is_online = False
        db.session.commit()
        print(f"❌ {player.name} отключился")

@socketio.on('start_battle')
def handle_start_battle():
    if not current_user.is_authenticated:
        return
    
    player = current_user.player
    location_mobs = MOBS.get(player.current_location, MOBS["деревня"])
    
    # Выбираем моба под уровень игрока
    available_mobs = [m for m in location_mobs if m['level'] <= player.level + 2]
    if not available_mobs:
        available_mobs = location_mobs
    
    mob_data = random.choice(available_mobs).copy()
    mob_data['current_hp'] = mob_data['hp']
    
    battles[player.id] = {
        'mob': mob_data,
        'turn': 'player',
        'stun': 0
    }
    
    emit('battle_start', {
        'mob': {
            'name': mob_data['name'], 
            'hp': mob_data['hp'], 
            'max_hp': mob_data['max_hp'],
            'level': mob_data['level']
        },
        'player_hp': player.hp,
        'player_max_hp': player.max_hp,
        'player_stamina': player.stamina,
        'player_max_stamina': player.max_stamina
    })
    emit('battle_log', {'message': f'⚔️ На вас напал {mob_data["name"]} (Уровень {mob_data["level"]})!'})

@socketio.on('battle_action')
def handle_battle_action(data):
    if not current_user.is_authenticated:
        return
    
    player = current_user.player
    action = data.get('action')
    
    if player.id not in battles:
        emit('battle_error', {'message': '❌ Бой не начат!'})
        return
    
    battle = battles[player.id]
    mob = battle['mob']
    
    # Проверка стана
    if battle.get('stun', 0) > 0:
        battle['stun'] -= 1
        emit('battle_log', {'message': '😵 Вы оглушены и пропускаете ход!'})
        battle['turn'] = 'mob'
        socketio.sleep(0.5)
        mob_turn(player, battle)
        return
    
    if battle['turn'] != 'player':
        emit('battle_error', {'message': '⏳ Сейчас ход врага!'})
        return
    
    damage = 0
    stamina_cost = 0
    action_name = ""
    stun_chance = 0
    
    # Обработка действий
    if action == 'attack':
        damage = random.randint(12, 22) + player.attack
        action_name = "Обычная атака"
        stamina_cost = 0
        
    elif action == 'strong_attack':
        if player.stamina < 20:
            emit('battle_error', {'message': '💙 Нужно 20 стамины!'})
            return
        damage = random.randint(35, 55) + player.attack
        action_name = "Сильный удар"
        stamina_cost = 20
        stun_chance = 15
        
    elif action == 'defend':
        if player.stamina < 15:
            emit('battle_error', {'message': '💙 Нужно 15 стамины!'})
            return
        action_name = "Защитная стойка"
        stamina_cost = 15
        battle['defense_bonus'] = 20
        emit('battle_log', {'message': f'🛡️ Защита +20 на 1 ход!'})
        
    elif action == 'fast_attack':
        if player.stamina < 12:
            emit('battle_error', {'message': '💙 Нужно 12 стамины!'})
            return
        damage = random.randint(20, 35) + player.attack
        action_name = "Быстрый удар"
        stamina_cost = 12
        player.stamina += 5
    
    # Нанесение урона
    if damage > 0:
        is_critical = random.randint(1, 100) <= player.crit_chance
        if is_critical:
            damage = int(damage * (player.crit_damage / 100))
            emit('battle_log', {'message': f'💥 КРИТИЧЕСКИЙ УДАР! x{player.crit_damage/100}'})
        
        # Защита моба
        damage = max(1, damage - mob.get('defense', 0))
        battle['mob']['current_hp'] -= damage
        player.stamina -= stamina_cost
        
        emit('battle_log', {'message': f'⚔️ {action_name} нанёс {damage} урона!'})
        
        # Шанс оглушить
        if stun_chance > 0 and random.randint(1, 100) <= stun_chance:
            battle['mob_stun'] = 1
            emit('battle_log', {'message': '😵 Враг оглушен на следующий ход!'})
        
        db.session.commit()
    
    # Проверка победы
    if battle['mob']['current_hp'] <= 0:
        end_battle(player, battle, True)
        return
    
    # Обновление UI
    emit('battle_update', {
        'player_hp': player.hp,
        'player_stamina': player.stamina,
        'mob_hp': battle['mob']['current_hp']
    })
    
    # Ход моба
    battle['turn'] = 'mob'
    socketio.sleep(0.5)
    mob_turn(player, battle)

def mob_turn(player, battle):
    mob = battle['mob']
    
    # Проверка стана моба
    if battle.get('mob_stun', 0) > 0:
        battle['mob_stun'] = 0
        emit('battle_log', {'message': '😵 Враг оглушен и пропускает ход!'})
        battle['turn'] = 'player'
        emit('battle_log', {'message': '🔥 Ваш ход!'})
        return
    
    defense_bonus = battle.get('defense_bonus', 0)
    
    # Выбор атаки моба
    if random.randint(1, 100) <= 30 and mob.get('level', 1) >= 3:
        # Сильная атака
        mob_damage = random.randint(mob['attack'] + 5, mob['attack'] + 15)
        action_text = f"💪 {mob['name']} использует мощную атаку!"
    else:
        # Обычная атака
        mob_damage = random.randint(mob['attack'] - 5, mob['attack'] + 5)
        action_text = f"💔 {mob['name']} атакует!"
    
    mob_damage = max(3, mob_damage - (player.defense + defense_bonus) // 2)
    
    # Шанс уклонения
    if random.randint(1, 100) <= player.dodge_chance:
        emit('battle_log', {'message': f'✨ Вы уклонились от атаки {mob["name"]}!'})
        mob_damage = 0
    else:
        emit('battle_log', {'message': action_text})
        player.hp -= mob_damage
        emit('battle_log', {'message': f'💔 {mob_damage} урона!'})
    
    # Регенерация
    player.stamina = min(player.max_stamina, player.stamina + 15)
    db.session.commit()
    
    # Проверка поражения
    if player.hp <= 0:
        end_battle(player, battle, False)
        return
    
    # Обновление UI
    emit('battle_update', {
        'player_hp': player.hp,
        'player_stamina': player.stamina,
        'mob_hp': battle['mob']['current_hp']
    })
    
    battle['defense_bonus'] = 0
    battle['turn'] = 'player'
    emit('battle_log', {'message': '🔥 Ваш ход! Выберите действие.'})

def end_battle(player, battle, victory):
    mob = battle['mob']
    
    if victory:
        exp_gain = mob['exp']
        gold_gain = mob['gold']
        player.exp += exp_gain
        player.gold += gold_gain
        player.monsters_killed += 1
        
        level_up = False
        while player.exp >= player.next_exp:
            player.level += 1
            player.exp -= player.next_exp
            player.next_exp = int(player.next_exp * 1.2)
            player.skill_points += 1
            player.max_hp += 25
            player.hp = player.max_hp
            player.max_stamina += 10
            player.stamina = player.max_stamina
            player.attack += 5
            player.defense += 2
            level_up = True
        
        player.apply_skill_bonuses()
        db.session.commit()
        
        emit('battle_log', {'message': f'🎉 ПОБЕДА! +{exp_gain} опыта, +{gold_gain} золота'})
        if level_up:
            emit('battle_log', {'message': f'🌟 УРОВЕНЬ {player.level}! +1 очко навыка! 🌟'})
    else:
        player.hp = player.max_hp // 2
        player.current_location = "деревня"
        db.session.commit()
        emit('battle_log', {'message': '💀 ВЫ ПОВЕРЖЕНЫ! Возвращение в деревню...'})
        emit('location_changed', {'loc': 'деревня'})
    
    emit('player_update', player.to_dict())
    emit('battle_end', {'victory': victory})
    del battles[player.id]

@socketio.on('use_potion')
def handle_use_potion(data):
    if not current_user.is_authenticated:
        return
    
    player = current_user.player
    potion_type = data.get('type')
    
    if player.id not in battles:
        emit('battle_error', {'message': '❌ Вы не в бою!'})
        return
    
    battle = battles[player.id]
    
    if battle['turn'] != 'player':
        emit('battle_error', {'message': '⏳ Сейчас не ваш ход!'})
        return
    
    items = player.inventory.split(",") if player.inventory else []
    
    if potion_type == 'health':
        for i, item in enumerate(items):
            if 'Зелье здоровья' in item:
                count = int(item.split('x')[1]) if 'x' in item else 1
                if count > 1:
                    items[i] = f"Зелье здоровья x{count-1}"
                else:
                    items.pop(i)
                
                heal = 50
                player.hp = min(player.max_hp, player.hp + heal)
                player.inventory = ",".join(items)
                db.session.commit()
                emit('battle_log', {'message': f'💚 +{heal} HP!'})
                emit('battle_update', {
                    'player_hp': player.hp,
                    'player_stamina': player.stamina,
                    'mob_hp': battle['mob']['current_hp']
                })
                
                battle['turn'] = 'mob'
                socketio.sleep(0.5)
                mob_turn(player, battle)
                return
    
    elif potion_type == 'energy':
        for i, item in enumerate(items):
            if 'Зелье энергии' in item:
                count = int(item.split('x')[1]) if 'x' in item else 1
                if count > 1:
                    items[i] = f"Зелье энергии x{count-1}"
                else:
                    items.pop(i)
                
                restore = 40
                player.stamina = min(player.max_stamina, player.stamina + restore)
                player.inventory = ",".join(items)
                db.session.commit()
                emit('battle_log', {'message': f'💙 +{restore} энергии!'})
                emit('battle_update', {
                    'player_hp': player.hp,
                    'player_stamina': player.stamina,
                    'mob_hp': battle['mob']['current_hp']
                })
                return
    
    emit('battle_error', {'message': 'Нет зелья!'})

@socketio.on('global_chat')
def handle_global_chat(data):
    if current_user.is_authenticated:
        message = data.get('message', '')[:200]
        if message:
            emit('chat_message', {
                'name': current_user.player.name,
                'message': message,
                'time': datetime.now().strftime("%H:%M")
            }, room='global')

@socketio.on('change_location')
def handle_location(data):
    if not current_user.is_authenticated:
        return
    
    loc = data.get('loc')
    valid = ["деревня", "лес", "пещера", "арена"]
    
    if loc not in valid:
        return
    
    player = current_user.player
    
    if player.id in battles:
        emit('battle_error', {'message': '❌ Нельзя сменить локацию в бою!'})
        return
    
    old_loc = player.current_location
    player.current_location = loc
    db.session.commit()
    
    leave_room(old_loc)
    join_room(loc)
    
    emit('location_changed', {'loc': loc})
    emit('battle_log', {'message': f'🌍 Вы отправились в {loc}'})

# === Создание БД ===
with app.app_context():
    db.create_all()
    print("✅ Сервер запущен с балансом и навыками!")

if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0', port=80, allow_unsafe_werkzeug=True)
