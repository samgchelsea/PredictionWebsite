from flask import Flask, render_template, request, redirect, g, session
import bcrypt
import sqlite3
from sqlite3 import IntegrityError
import datetime
import time

''' 
TO DO:
	1. BE ABLE TO SEE EACH OTHERS PREDICTIONS FOR PREVIOUS WEEKS
	2. DO THE CHAMPIONSHIP TABLE
			- NEED TO DO MOSTLY THE SAME AS THE LEAGUE TABLE
				- TABLE:
					POS
					TEAM NAME
					GAMES PLAYED
					AMOUNT CORRECT	
					PERCENTAGE OF PREDS CORRECT 

	3. DO THE CUP RUN
'''

app = Flask(__name__, static_url_path='/static')

app.secret_key = '217cb6ed8bb0cd42d7804673d8a5346f'

actualWeek = 31
week = 2
games = [1,2,3,4,5,6]
played = 0
weekUpdater = week + actualWeek

@app.route("/addComment", methods=['POST'])
def pageReloader():
	print("This happens")
	if 'username' in session:
		comment = request.form['comment']
		username = session['username']
		timeOfComment = datetime.datetime.now()
		commentMonth = timeOfComment.month
		commentDay = timeOfComment.day
		commentHour = timeOfComment.hour
		commentMinute = timeOfComment.minute
		timeOfComment = f"0{commentMonth}-{commentDay} {commentHour}:{commentMinute}"
		conn = getDatabase()
		cursor = conn.cursor()
		cursor.execute("SELECT team_name FROM users WHERE username = ?",(username,))
		team_name = cursor.fetchone()
		print("This is the team name",team_name)
		if team_name != (None,):
			cursor.execute("INSERT INTO comments (username, comment, timeOfComment) VALUES (?,?,?)", (team_name[0], comment, timeOfComment))
			conn.commit()
			return redirect('/load')
		elif team_name == (None,):
			return "You can only comment if you are a registered member of the league."
		else:
			return "Error posting comment. Please try again later."
	else:
		return "You can only comment if you are logged in."


# WEEKLY SCORE CALCULATION UGHHHHHHHH
def scoreCalculation():
	conn = getDatabase()
	cursor = conn.cursor()
	global week
	# Get all the users in the users database
	cursor.execute('SELECT DISTINCT username FROM predictions WHERE week = ?', ((week-1),))
	users = cursor.fetchall()
	for user in users:
		username = user[0]
		print(username)
		cursor.execute('SELECT * FROM predictions WHERE username = ? AND week = ?', (username, (week-1)))
		user_predictions = cursor.fetchone()
		if user_predictions:
			# Is the user home or away
			cursor.execute('SELECT team_name FROM users WHERE username = ?', (username,))
			team_name = cursor.fetchone()
			print(team_name)
			if team_name:
				#Find if the user is at home or away
				cursor.execute('SELECT COUNT(*) FROM playerFixtures WHERE week = ? AND homeUser = ?', ((week-1), team_name[0]))
				homeUser = cursor.fetchone()[0] > 0
				
				num_predictions = 6 if homeUser else 5
				totalScore = 0
				for i in range(1, num_predictions+1):
					prediction = user_predictions[i + 3]
					print (prediction, "END OF PREDICTION")

					match_id = (i + (6* (week-2)))
					cursor.execute('SELECT result FROM realFixtures WHERE match_id = ?', (match_id,))
					real_result_row = cursor.fetchone()
					print("Real results ",real_result_row)
					if real_result_row:
						real_result = real_result_row[0]
						prediction = user_predictions[i+2]
						if prediction == real_result:
							totalScore += 1
					print("Total score ",totalScore)

				# Has this user made predictions for this week already?
				print("im from the future Statement ", username, " week ", (week-1))
				cursor.execute('SELECT * FROM weeklyScores WHERE username =? AND week = ?', (username,(week-1)))
				existing_scores = cursor.fetchone()
				print(existing_scores)
				if existing_scores:
					for existing_score in existing_scores:
						if existing_score is not None and existing_score[1] == (week - 1):
							cursor.execute('UPDATE weeklyScores SET totalScore = ?', (0))
							cursor.execute('UPDATE weeklyScores SET username = ?, week = ?, totalScore = ?', (username,(week-1),totalScore))
							print("SAMGOODWIN ISAWESOMMME")
						else:
							print("No existing score for",username)
							cursor.execute('INSERT INTO weeklyScores (username, week, totalScore) VALUES (?,?,?)', (username,(week-1),totalScore))
				else:
					print("I am happening")
					cursor.execute('UPDATE weeklyScores SET username = ?, week = ?, totalScore = ?', (username,(week-1),totalScore))


				#Find the team name of the user
				cursor.execute('SELECT team_name FROM users WHERE username = ?', (username,))
				team_name = cursor.fetchone()
				print("This line happens")
				if homeUser:
					cursor.execute('UPDATE playerFixtures SET homeGoals = ? WHERE homeUser = ? AND week = ?', (totalScore, team_name[0],(week-1)))
					print("Success")
				elif not homeUser:
					cursor.execute('UPDATE playerFixtures SET awayGoals = ? WHERE awayUser = ? AND week = ?', (totalScore, team_name[0],(week-1)))
					print("Success Two")

				cursor.execute('UPDATE playerFixtures SET goalDifference = homeGoals - awayGoals')
				cursor.execute("""
					UPDATE playerFixtures
					SET homePoints = CASE
	                					WHEN homeGoals > awayGoals THEN 3
	                					WHEN homeGoals = awayGoals THEN 1
	                					ELSE 0
	             					END,
						awayPoints = CASE
	                					WHEN homeGoals < awayGoals THEN 3
	                					WHEN homeGoals = awayGoals THEN 1
	                					ELSE 0
	             					END
				""")
		


def winUpdater(cursor,week):
	winUpdater = """
		UPDATE leagueTable
        SET Won = (
            SELECT COUNT(*)
            FROM playerFixtures
            WHERE week = ?
		    AND (
		    	(homeGoals > awayGoals AND homeUser = leagueTable.team_name)
		    OR (homeGoals < awayGoals AND awayUser = leagueTable.team_name)
		    )
		) + (
            SELECT COALESCE(SUM(ct.Won), 0)
            FROM currentTable AS ct
            WHERE ct.team_name = leagueTable.team_name  
		) 
	"""

	cursor.execute(winUpdater, (week,))

def drawUpdater(cursor,week):
	drawUpdater = ("""
		UPDATE leagueTable
        SET Drawn = (
            SELECT COUNT(*)
            FROM playerFixtures
            WHERE week = ?
		    AND (
		    	(homeGoals == awayGoals AND homeUser == leagueTable.team_name)
		    OR (homeGoals == awayGoals AND awayUser == leagueTable.team_name)
		    )
		) + (
            SELECT COALESCE(SUM(ct.Drawn), 0)
            FROM currentTable AS ct
            WHERE ct.team_name = leagueTable.team_name
        )
	""")
	cursor.execute(drawUpdater, (week,))

def lossUpdater(cursor,week):
	lossUpdater_query = """
        UPDATE leagueTable
        SET Lost = (
            SELECT COUNT(*)
            FROM playerFixtures
            WHERE week = ?
            AND (
                (homeGoals > awayGoals AND awayUser = leagueTable.team_name)
                OR (homeGoals < awayGoals AND homeUser = leagueTable.team_name)
            )
        ) + (
            SELECT COALESCE(SUM(ct.Lost), 0)
            FROM currentTable AS ct
            WHERE ct.team_name = leagueTable.team_name
        )
    """
	cursor.execute(lossUpdater_query, (week,))

def tableUpdate(week,played):
	conn = getDatabase()
	cursor = conn.cursor()

	weekCounter = week

	# Update Points
	for w in range(0,weekCounter+1):
		
		# Update Points

		cursor.execute("""
			UPDATE leagueTable AS lt
			SET Points = (
	    		SELECT COALESCE(SUM(pf.awayPoints), 0) 
	    		FROM playerFixtures AS pf 
	    		WHERE pf.awayUser = lt.team_name AND pf.week = ?
			) + (
	    		SELECT COALESCE(SUM(pf.homePoints), 0) 
	    		FROM playerFixtures AS pf 
	    		WHERE pf.homeUser = lt.team_name AND pf.week = ?
	    	) + (
	            SELECT COALESCE(SUM(ct.Points), 0)
	            FROM currentTable AS ct
	            WHERE ct.team_name = lt.team_name
        	);
		""",(w,w))
	
		# Update GF

		cursor.execute("""
			UPDATE leagueTable AS lt
			SET GF = (
	    		SELECT COALESCE(SUM(pf.awayGoals), 0) 
	    		FROM playerFixtures AS pf 
	    		WHERE pf.awayUser = lt.team_name AND pf.week = ?
			) + (
	    		SELECT COALESCE(SUM(pf.homeGoals), 0) 
	    		FROM playerFixtures AS pf 
	    		WHERE pf.homeUser = lt.team_name AND pf.week = ?
			) + (
	            SELECT COALESCE(SUM(ct.GF), 0)
	            FROM currentTable AS ct
	            WHERE ct.team_name = lt.team_name
        	);
		""",(w,w))

		# Update GA

		cursor.execute("""
			UPDATE leagueTable AS lt
			SET GA = (
	    		SELECT COALESCE(SUM(pf.homeGoals), 0) 
	    		FROM playerFixtures AS pf 
	    		WHERE pf.awayUser = lt.team_name AND pf.week = ?
			) + (
	    		SELECT COALESCE(SUM(pf.awayGoals), 0) 
	    		FROM playerFixtures AS pf 
	    		WHERE pf.homeUser = lt.team_name AND pf.week = ?
			) + (
	            SELECT COALESCE(SUM(ct.GA), 0)
	            FROM currentTable AS ct
	            WHERE ct.team_name = lt.team_name
        	);
		""",(w,w))

		# Update GD
		cursor.execute("""
			UPDATE leagueTable
			SET GD = CASE
						WHEN (GF-GA) >= 0 THEN '+' || (GF-GA)
						ELSE '-' || ABS(GF-GA)
					END;
			""")

		weekCounter = weekCounter + 1
		conn.commit()


		# Update Played, Won, Drawn, Lost columns
		query = ("""
			SELECT week,
				COUNT(*) AS total_rows,
				COUNT(result) AS rows_with_result
			FROM realFixtures
			WHERE week = ?
			GROUP BY week;
		""")

		cursor.execute(query, (week,))

		queryResult = cursor.fetchone()
		if queryResult is not None:
			# If total games in week is equal to games with confirmed results the current week has been played
			if queryResult[1] == queryResult[2]:
				if week == 0:
					fullReset = ("""
						DELETE FROM leagueTable;
					""")
					cursor.execute(fullReset)
					weekZeroReset = ("""
						INSERT INTO leagueTable (team_name, Played, Won, Drawn, Lost, GF, GA, GD, Points)
						SELECT team_name, Played, Won, Drawn, Lost, GF, GA, GD, Points
						FROM currentTable;
					""")
					cursor.execute(weekZeroReset)
					conn.commit()
				else:					
					played = week
					playedUpdater = ("""
						UPDATE leagueTable
						SET Played = ?;
						""")
					cursor.execute(playedUpdater, ((played+actualWeek),))
					# Calculates games won, drawn and lost
					# Update Won,
					winUpdater(cursor,week)
					drawUpdater(cursor,week)
					lossUpdater(cursor,week)
					conn.commit()
			# If total games in week is not equal to games with confirmed results a player game hasn't been played this week
			elif (queryResult[1] != queryResult[2]) and week >= 0:
				if week == 0 or week == 1:
					fullReset = ("""
						DELETE FROM leagueTable;
					""")
					cursor.execute(fullReset)
					weekZeroReset = ("""
						INSERT INTO leagueTable (team_name, Played, Won, Drawn, Lost, GF, GA, GD, Points)
						SELECT team_name, Played, Won, Drawn, Lost, GF, GA, GD, Points
						FROM currentTable;
					""")
					cursor.execute(weekZeroReset)
					conn.commit()
				elif week != 1 or week != 0:
					played = (week - 1)
					playedUpdater = ("""
						UPDATE leagueTable
						SET Played = ?;
						""")
					cursor.execute(playedUpdater, (((played-1)+actualWeek),))
					# Calculates games won, drawn and lost for incomplete week
					week = week-1
					winUpdater(cursor,week)
					drawUpdater(cursor,week)
					lossUpdater(cursor,week)
					conn.commit()
			
		# UPDATE THE CHAMPIONSHIP TABLE
		


# TABLE MAKER AND SHAKER
def leagueTable(week,played):
	tableUpdate(week,played)
	conn = getDatabase()
	cursor = conn.cursor()
	cursor.execute("""
    WITH RankedRows AS (
        SELECT 
            ROW_NUMBER() OVER (ORDER BY l.points DESC, l.GD DESC, l.GF DESC, GA ASC, team_name) AS position,
            l.team_name,
            l.Played,
            l.Won,
            l.Drawn,
            l.Lost,
            l.GF,
            l.GA,
            l.GD,
            l.points
        FROM leagueTable l
    )
    SELECT *
    FROM RankedRows
    WHERE position = 1
    ORDER BY position;
	""")
	championRow = cursor.fetchone()

	cursor.execute("""
    WITH RankedRows AS (
        SELECT 
            ROW_NUMBER() OVER (ORDER BY l.points DESC, l.GD DESC, l.GF DESC, l.GA ASC, team_name) AS position,
            l.team_name,
            l.Played,
            l.Won,
            l.Drawn,
            l.Lost,
            l.GF,
            l.GA,
            l.GD,
            l.points
        FROM leagueTable l
    )
    SELECT *
    FROM RankedRows
    WHERE position <= 4 AND position != 1
    ORDER BY position;
	""")
	firstfourRows = cursor.fetchall()

	cursor.execute("""
    WITH RankedRows AS (
        SELECT 
            ROW_NUMBER() OVER (ORDER BY l.points DESC, l.GD DESC, l.GF DESC, l.GA ASC, team_name) AS position,
            l.team_name,
            l.Played,
            l.Won,
            l.Drawn,
            l.Lost,
            l.GF,
            l.GA,
            l.GD,
            l.points
        FROM leagueTable l
    )
    SELECT *
    FROM RankedRows
    WHERE position >= 5 AND position <= 10
    ORDER BY position;
	""")
	europeRows = cursor.fetchall()	

	cursor.execute("""
    WITH RankedRows AS (
        SELECT 
            ROW_NUMBER() OVER (ORDER BY l.points DESC, l.GD DESC, l.GF DESC, l.GA ASC, team_name) AS position,
            l.team_name,
            l.Played,
            l.Won,
            l.Drawn,
            l.Lost,
            l.GF,
            l.GA,
            l.GD,
            l.points
        FROM leagueTable l
    )
    SELECT *
    FROM RankedRows
    WHERE position > 10 AND position <= 12
    ORDER BY position;
	""")
	whyexistRows = cursor.fetchall()	

	cursor.execute("""
    WITH RankedRows AS (
        SELECT 
            ROW_NUMBER() OVER (ORDER BY l.points DESC, l.GD DESC, l.GF DESC, l.GA ASC, team_name) AS position,
            l.team_name,
            l.Played,
            l.Won,
            l.Drawn,
            l.Lost,
            l.GF,
            l.GA,
            l.GD,
            l.points
        FROM leagueTable l
    )
    SELECT *
    FROM RankedRows
    WHERE position > 12 AND position <= 17
    ORDER BY position;
	""")
	restoftheRows = cursor.fetchall()		

	cursor.execute("""
	    WITH RankedRows AS (
	        SELECT 
	            ROW_NUMBER() OVER (ORDER BY l.points DESC, l.GD DESC, l.GF DESC, l.GA ASC, team_name) AS position,
	            l.team_name,
	            l.Played,
	            l.Won,
	            l.Drawn,
            	l.Lost,
	            l.GF,
	            l.GA,
	            l.GD,
	            l.points
	        FROM leagueTable l
	    )
	    SELECT *
	    FROM RankedRows
	    WHERE position > 17
	    ORDER BY position;
	""")
	lastRows = cursor.fetchall()
	# Champhionship table which is useless omg why does this even exist who knows for sure i dont
	conn = getDatabase()
	cursor = conn.cursor()
	cursor.execute("""
		WITH RankedRows AS (
			SELECT
				ROW_NUMBER() OVER (ORDER BY ct.percentage DESC, ct.numCorrect DESC, ct.teamName) AS position,
				ct.teamName,
				ct.numCorrect,
				ct.percentage
			FROM currentChampion ct
			)
		SELECT *
		FROM RankedRows
		ORDER BY position;
	""")
	championshipTableRows = cursor.fetchall()
	print(championshipTableRows)
	username = session['username']
	return render_template('table.html', username=username, championshipTableRows=championshipTableRows, firstfourRows=firstfourRows, europeRows=europeRows, whyexistRows=whyexistRows, restoftheRows=restoftheRows, lastRows=lastRows, championRow=championRow)

# Fetch all the comments for the database
def getCommentsFromDB():
	conn = getDatabase()
	cursor = conn.cursor()
	cursor.execute("SELECT username, comment, timeOfComment FROM comments ORDER by id ASC")
	comments = cursor.fetchall()
	cursor.close()
	return comments

# DISPLAY HOMEPAGE  
@app.route('/')
def home():
	conn = getDatabase()
	cursor = conn.cursor()
	scoreCalculation()
	comments = getCommentsFromDB()
	tableUpdate(week,played)
	fixtures = getFixtureList()
	homeResults = homeResultList()
	print(homeResults)
	cursor.execute("""
    WITH RankedRows AS (
        SELECT 
            ROW_NUMBER() OVER (ORDER BY l.points DESC, l.GD DESC, l.GF DESC, GA ASC) AS position,
            l.team_name,
            l.played,
            l.GD,
            l.points
        FROM leagueTable l
    )
    SELECT *
    FROM RankedRows
    WHERE position <= 20
    ORDER BY position;
	""")
	homepageRows = cursor.fetchall()
	if 'username' in session:
		# User is logged in
		return render_template('GoodwinFootball.html', fixtures=fixtures, comments=comments, homeResults=homeResults, weekUpdater=weekUpdater, username=session['username'], homepageRows=homepageRows)
	else:
		# User is not logged in
		return render_template('login.html', fixtures=fixtures, comments=comments, homeResults=homeResults, weekUpdater=weekUpdater, homepageRows=homepageRows)





# LOGIN BUTTON DISPLAYS LOGIN PAGE
@app.route('/login-page')
def login():
    return render_template('login.html')

# REGISTER BUTTON DISPLAYS REGISTER PAGE
@app.route('/registration-page')
def registration():
    return render_template('registration.html')

@app.route('/load')
def load():
	scoreCalculation()
	tableUpdate(week,played)
	return render_template('success.html')

# LOGOUT SYSTEM
@app.route('/logout')
def logout():
	session.pop('username', None)
	return redirect('/load') 


# Function for hashing the password
def hash_password(password):
	salt = bcrypt.gensalt()
	hashed_password_bytes = bcrypt.hashpw(password.encode('utf-8'), salt)
	# Convert it back to a string
	hashed_password = hashed_password_bytes.decode('utf-8')
	return hashed_password


# Database name
DATABASE = 'predictions.db'

def getDatabase():
	db = getattr(g, '_database', None)
	if db is None:
		db = g._database = sqlite3.connect(DATABASE)
	return db

@app.teardown_appcontext
def close_connection(exception):
	db = getattr(g, '_database', None)
	if db is not None:
		db.close()


# REGISTRATION SYSTEM

@app.route('/register', methods=['POST'])
def register():
	# Retrieves username from the user input
	username = request.form['username']
	passwordOne = request.form['passwordOne']
	passwordTwo = request.form['passwordTwo']
	
	# Checks if the passwords match
	if passwordOne != passwordTwo:
		error = ("Passwords do not match. Try again.")
		return render_template('registration.html', error=error)
	if ' ' in passwordOne:
		error = ("Password must not contain any spaces or indentations.")
		return render_template('registration.html', error=error)


	# Hash the password
	hashed_password = hash_password(passwordOne)
		
	try:
		conn = getDatabase()
		cursor = conn.cursor()
		cursor.execute('INSERT INTO users (username, hashed_password) VALUES (?, ?)', (username, hashed_password))
		conn.commit()
		return redirect('/load')

	except sqlite3.IntegrityError:
		error = ("Username already exists. Please try again!")
		return render_template('registration.html', error=error)


# LOGIN SYSTEM

@app.route('/login', methods=['POST'])
def authenticate():
	username = request.form['username']
	password = request.form['password']

	conn = getDatabase()
	cursor = conn.cursor()
	cursor.execute('SELECT username, hashed_password FROM users WHERE username = ?', (username,))
	user = cursor.fetchone()

	if user:
		stored_username, hashed_password = user
		if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
			session['username'] = username
			return redirect('/load')
		else:
			error = "Incorrect password. Please try again."
			return render_template('login.html', error=error)
	else:
		error = "User not found. Please try again."
		return render_template('login.html', error=error)



# Button to increase prediction week

@app.route('/addWeek')
def addWeek():
	global week
	global weekUpdater
	print(weekUpdater)
	if weekUpdater < 38:
		weekUpdater += 1
		print(weekUpdater, "im mr meeseeks look at me")

	else:
		weekUpdater = weekUpdater
	return 'Week incremented.'

@app.route('/minusWeek')
def minusWeek():
	global week
	global weekUpdater
	if weekUpdater > (week + actualWeek):
		weekUpdater -= 1
	else:
		weekUpdater = weekUpdater
	return 'Week before.'

@app.route('/addResultWeek')
def addResultWeek():
	global week
	global weekUpdater
	print(weekUpdater)
	if weekUpdater < 38:
		weekUpdater += 1
		print(weekUpdater, "im mr meeseeks look at me")

	else:
		weekUpdater = weekUpdater
	return 'Week incremented.'

@app.route('/minusResultWeek')
def minusResultWeek():
	global week
	global weekUpdater
	if weekUpdater > (actualWeek):
		weekUpdater -= 1
	else:
		weekUpdater = weekUpdater
	return 'Week before.'

# PREDICTION SYSTEM

@app.route('/predict', methods=['GET'])
def predict():
	try:
		print(week)
		conn=getDatabase()
		cursor=conn.cursor()
		cursor.execute('SELECT team_name FROM users WHERE username = ?', (session['username'],))
		team_name = cursor.fetchone()

		if team_name:
			#Find if the user is at home or away
			cursor.execute('SELECT COUNT(*) FROM playerFixtures WHERE week = ? AND homeUser = ?', (week, team_name[0]))
			homeUser = cursor.fetchone()[0] > 0

			# Find the correct games to take from the specified week
			start_match_id = ((weekUpdater-actualWeek)-1)*6 + 1
			end_match_id = (weekUpdater-actualWeek)*6
			toPredict = list(range(start_match_id,end_match_id + 1))

			#Take the 6 games from the specified week
			placeholders = ','.join('?' for _ in toPredict)
			query = f'SELECT * FROM realFixtures WHERE match_id IN ({placeholders})'
			print("SQL query: ",query)
			cursor.execute(query, tuple(toPredict))
			fixtures = cursor.fetchall()
			print(fixtures)
			fixtures_data = []
			print(type(fixtures_data))

			# Goes through each row and takes relevant data
			for fixture in fixtures:
				fixture_data = {
					'match_id': fixture[0],
					'homeTeam': fixture[1],
					'awayTeam': fixture[2]
				}
				fixtures_data.append(fixture_data)
			conn.close()

			# Ensures that if user is at home then they receive 6 games
			if homeUser:
				if len(fixtures) > 6:
					fixtures_data = fixtures_data[:6]
			# If user is away they receive 5.
			else:
				if len(fixtures) > 5:
					fixtures_data = fixtures_data[:5]


			print ("Fixtures: ", fixtures_data)
			username = session['username']
			return render_template('predictions.html', fixtures=fixtures_data, week=week, weekUpdater=weekUpdater, username=username)

		else:
			return "Users team not found."

	except Exception as e:
		app.logger.error(f"An error occured: {e}")

	return"An unexpected error occured"


@app.route('/submit_predictions',methods=['POST'])
def submit_predictions():
	try:
		# Get prediction data from the form
		predictions = request.form.getlist('predicted_scores[]')

		#Find which user is making the predictions
		conn = getDatabase()
		cursor = conn.cursor()
		cursor.execute('SELECT user_id FROM users WHERE username = ?', (session['username'],))
		user_id = cursor.fetchone()[0]

		# Has this user made predictions for this week already?

		cursor.execute('SELECT * FROM predictions WHERE username =? AND week = ? ', (session['username'], week))
		existing_predictions = cursor.fetchone()

		if existing_predictions:
			cursor.execute('DELETE FROM predictions WHERE username = ? AND week = ?', (session['username'], week))


		# Is the user home or away
		cursor.execute('SELECT team_name FROM users WHERE username = ?', (session['username'],))
		team_name = cursor.fetchone()

		if team_name:
			#Find if the user is at home or away
			cursor.execute('SELECT COUNT(*) FROM playerFixtures WHERE week = ? AND homeUser = ?', (week, team_name[0]))
			homeUser = cursor.fetchone()[0] > 0


		# Now i neeed to insert the predictions into the database
		if homeUser:
			cursor.execute('INSERT INTO predictions (user_id, username, is_home, predictionOne, predictionTwo, predictionThree, predictionFour, predictionFive, predictionSix, week) VALUES (?,?,?,?,?,?,?,?,?,?)', (user_id,session['username'],homeUser,*predictions, week))

		else:
			cursor.execute('INSERT INTO predictions (user_id, username, is_home, predictionOne, predictionTwo, predictionThree, predictionFour, predictionFive, week) VALUES (?,?,?,?,?,?,?,?,?)', (user_id,session['username'],homeUser,*predictions, week))

		conn.commit()
		conn.close()

		# Redirect to a success page
		return redirect('/load')

		# Exceptions or errors
	except Exception as e:
		app.logger.error(f"An error occured: {e}")

	return"An unexpected error occured"

@app.route('/leagueTable')
def league_table():
	tableUpdate(week,played)
	return leagueTable(week,played)


# DISPLAY THE FIXTURES PAGE
@app.route('/fixtures')
def fixtures():
	username = None
	if 'username' in session:
		username = session['username']
	fixtures_data = getFixtureList()
	return render_template('fixtures.html', username = username, fixtures = fixtures_data, weekUpdater = weekUpdater, week=week)

@app.route('/results')
def results():
	username = None
	if 'username' in session:
		username = session['username']
	results = getResultList()
	return render_template('results.html', username = username, results = results, weekUpdater = weekUpdater, week=week)


def getFixtureList():
	conn = getDatabase()
	cursor = conn.cursor()
	getFixtures = ("""
		SELECT homeUser, awayUser
		FROM playerFixtures
		WHERE week = ?
	""")
	cursor.execute(getFixtures,((weekUpdater - actualWeek),))
	fixtures = cursor.fetchall()
	return fixtures

def getResultList():
	conn = getDatabase()
	cursor = conn.cursor()
	global week
	global weekUpdater
	print("Mr Sam look: ", weekUpdater)
	getResults = ("""
		SELECT homeUser, homeGoals, awayGoals, awayUser
		FROM playerFixtures
		WHERE week = ?
	""")
	try:
		cursor.execute(getResults,((((weekUpdater - actualWeek)),)))
		unupdatedresults = cursor.fetchall()
		results=[]
		for unupdatedresult in unupdatedresults:
			homeGoals = unupdatedresult[1] if unupdatedresult[1] is not None else 0
			awayGoals = unupdatedresult[2] if unupdatedresult[2] is not None else 0
			result = (unupdatedresult[0], homeGoals, awayGoals, unupdatedresult[3])
			results.append(result)
		return results
	except Exception as e:
		print("Error fetching results: ", e)
		return None
	
def homeResultList():
	conn = getDatabase()
	cursor = conn.cursor()
	global week
	global actualWeek
	homeWeek = (week-1)
	print("Mr Sam look: ", homeWeek)
	gethomeResults = ("""
		SELECT homeUser, homeGoals, awayGoals, awayUser
		FROM playerFixtures
		WHERE week = ?
	""")
	try:
		cursor.execute(gethomeResults,(homeWeek,))
		unupdatedHomeresults = cursor.fetchall()
		homeResults=[]
		for unupdatedHomeresult in unupdatedHomeresults:
			homeGoals = unupdatedHomeresult[1] if unupdatedHomeresult[1] is not None else 0
			awayGoals = unupdatedHomeresult[2] if unupdatedHomeresult[2] is not None else 0
			homeResult = (unupdatedHomeresult[0], homeGoals, awayGoals, unupdatedHomeresult[3])
			homeResults.append(homeResult)
		print("OI", homeResults)
		return homeResults
	except Exception as e:
		print("Error fetching results: ", e)
		return None

if __name__ == '__main__':
	app.run(debug=True)

