
from sqlalchemy import *
import sqlalchemy.ansisql as ansisql
import sqlalchemy.databases.postgres as postgres
import sqlalchemy.databases.oracle as oracle
import sqlalchemy.databases.sqlite as sqlite
import sqlalchemy.databases.mysql as mysql

db = ansisql.engine()
#db = create_engine('mssql')

from testbase import PersistTest
import unittest, re

# the select test now tests almost completely with TableClause/ColumnClause objects,
# which are free-roaming table/column objects not attached to any database.  
# so SQLAlchemy's SQL construction engine can be used with no database dependencies at all.

table1 = table('mytable', 
    column('myid'),
    column('name'),
    column('description'),
)

table2 = table(
    'myothertable', 
    column('otherid'),
    column('othername'),
)

table3 = table(
    'thirdtable', 
    column('userid'),
    column('otherstuff'),
)

table4 = Table(
    'remotetable', db,
    Column('rem_id', Integer, primary_key=True),
    Column('datatype_id', Integer),
    Column('value', String(20)),
    schema = 'remote_owner'
)

users = table('users', 
    column('user_id'),
    column('user_name'),
    column('password'),
)

addresses = table('addresses', 
    column('address_id'),
    column('user_id'),
    column('street'),
    column('city'),
    column('state'),
    column('zip')
)

class SQLTest(PersistTest):
    def runtest(self, clause, result, engine = None, params = None, checkparams = None):
        c = clause.compile(parameters=params, engine=engine)
        self.echo("\nSQL String:\n" + str(c) + repr(c.get_params()))
        cc = re.sub(r'\n', '', str(c))
        self.assert_(cc == result, str(c) + "\n does not match \n" + result)
        if checkparams is not None:
            if isinstance(checkparams, list):
                self.assert_(c.get_params().values() == checkparams, "params dont match ")
            else:
                self.assert_(c.get_params() == checkparams, "params dont match" + repr(c.get_params()))
            
class SelectTest(SQLTest):
    def testtableselect(self):
        self.runtest(table1.select(), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable")

        self.runtest(select([table1, table2]), "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, \
myothertable.othername FROM mytable, myothertable")

    def testselectselect(self):
        """tests placing select statements in the column clause of another select, for the
        purposes of selecting from the exported columns of that select."""
        s = select([table1], table1.c.name == 'jack')
        #print [key for key in s.c.keys()]
        self.runtest(
            select(
                [s],
                s.c.myid == 7
            )
            ,
        "SELECT myid, name, description FROM (SELECT mytable.myid AS myid, mytable.name AS name, mytable.description AS description FROM mytable WHERE mytable.name = :mytable_name) WHERE myid = :myid")
        
        sq = select([table1])
        self.runtest(
            sq.select(),
            "SELECT myid, name, description FROM (SELECT mytable.myid AS myid, mytable.name AS name, mytable.description AS description FROM mytable)"
        )
        
        sq = select(
            [table1],
        ).alias('sq')

        self.runtest(
            sq.select(sq.c.myid == 7), 
            "SELECT sq.myid, sq.name, sq.description FROM \
(SELECT mytable.myid AS myid, mytable.name AS name, mytable.description AS description FROM mytable) AS sq WHERE sq.myid = :sq_myid"
        )
        
        sq = select(
            [table1, table2],
            and_(table1.c.myid ==7, table2.c.otherid==table1.c.myid),
            use_labels = True
        ).alias('sq')
        
        sqstring = "SELECT mytable.myid AS mytable_myid, mytable.name AS mytable_name, \
mytable.description AS mytable_description, myothertable.otherid AS myothertable_otherid, \
myothertable.othername AS myothertable_othername FROM mytable, myothertable \
WHERE mytable.myid = :mytable_myid AND myothertable.otherid = mytable.myid"

        self.runtest(sq.select(), "SELECT sq.mytable_myid, sq.mytable_name, sq.mytable_description, sq.myothertable_otherid, \
sq.myothertable_othername FROM (" + sqstring + ") AS sq")

        sq2 = select(
            [sq],
            use_labels = True
        ).alias('sq2')

        self.runtest(sq2.select(), "SELECT sq2.sq_mytable_myid, sq2.sq_mytable_name, sq2.sq_mytable_description, \
sq2.sq_myothertable_otherid, sq2.sq_myothertable_othername FROM \
(SELECT sq.mytable_myid AS sq_mytable_myid, sq.mytable_name AS sq_mytable_name, \
sq.mytable_description AS sq_mytable_description, sq.myothertable_otherid AS sq_myothertable_otherid, \
sq.myothertable_othername AS sq_myothertable_othername FROM (" + sqstring + ") AS sq) AS sq2")

    def testwheresubquery(self):
        self.runtest(
            table1.select(table1.c.myid == select([table2.c.otherid], table1.c.name == table2.c.othername)),
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = (SELECT myothertable.otherid AS otherid FROM myothertable WHERE mytable.name = myothertable.othername)"
        )

        self.runtest(
            table1.select(exists([1], table2.c.otherid == table1.c.myid)),
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE EXISTS (SELECT 1 FROM myothertable WHERE myothertable.otherid = mytable.myid)"
        )

        talias = table1.alias('ta')
        s = subquery('sq2', [talias], exists([1], table2.c.otherid == talias.c.myid))
        self.runtest(
            select([s, table1])
            ,"SELECT sq2.myid, sq2.name, sq2.description, mytable.myid, mytable.name, mytable.description FROM (SELECT ta.myid AS myid, ta.name AS name, ta.description AS description FROM mytable AS ta WHERE EXISTS (SELECT 1 FROM myothertable WHERE myothertable.otherid = ta.myid)) AS sq2, mytable")

        s = select([addresses.c.street], addresses.c.user_id==users.c.user_id, correlate=True).alias('s')
        self.runtest(
            select([users, s.c.street], from_obj=[s]),
            """SELECT users.user_id, users.user_name, users.password, s.street FROM users, (SELECT addresses.street AS street FROM addresses WHERE addresses.user_id = users.user_id) AS s""")

        
    def testcolumnsubquery(self):
        s = select([table1.c.myid], scalar=True, correlate=False)
        self.runtest(select([table1, s]), "SELECT mytable.myid, mytable.name, mytable.description, (SELECT mytable.myid AS myid FROM mytable) FROM mytable")

        s = select([table1.c.myid], scalar=True)
        self.runtest(select([table2, s]), "SELECT myothertable.otherid, myothertable.othername, (SELECT mytable.myid AS myid FROM mytable) FROM myothertable")
        

        zips = table('zips',
            column('zipcode'),
            column('latitude'),
            column('longitude'),
        )
        places = table('places',
            column('id'),
            column('nm')
        )
        zip = '12345'
        qlat = select([zips.c.latitude], zips.c.zipcode == zip, scalar=True, correlate=False)
        qlng = select([zips.c.longitude], zips.c.zipcode == zip, scalar=True, correlate=False)
 
        q = select([places.c.id, places.c.nm, zips.c.zipcode, func.latlondist(qlat, qlng).label('dist')],
                         zips.c.zipcode==zip,
                         order_by = ['dist', places.c.nm]
                         )

        self.runtest(q,"SELECT places.id, places.nm, zips.zipcode, latlondist((SELECT zips.latitude AS latitude FROM zips WHERE zips.zipcode = :zips_zipco_1), (SELECT zips.longitude AS longitude FROM zips WHERE zips.zipcode = :zips_zipco_2)) AS dist FROM places, zips WHERE zips.zipcode = :zips_zipcode ORDER BY dist, places.nm")
        
        zalias = zips.alias('main_zip')
        qlat = select([zips.c.latitude], zips.c.zipcode == zalias.c.zipcode, scalar=True)
        qlng = select([zips.c.longitude], zips.c.zipcode == zalias.c.zipcode, scalar=True)
        q = select([places.c.id, places.c.nm, zalias.c.zipcode, func.latlondist(qlat, qlng).label('dist')],
                         order_by = ['dist', places.c.nm]
                         )
        self.runtest(q, "SELECT places.id, places.nm, main_zip.zipcode, latlondist((SELECT zips.latitude AS latitude FROM zips WHERE zips.zipcode = main_zip.zipcode), (SELECT zips.longitude AS longitude FROM zips WHERE zips.zipcode = main_zip.zipcode)) AS dist FROM places, zips AS main_zip ORDER BY dist, places.nm")
            
    def testand(self):
        self.runtest(
            select(['*'], and_(table1.c.myid == 12, table1.c.name=='asdf', table2.c.othername == 'foo', "sysdate() = today()")), 
            "SELECT * FROM mytable, myothertable WHERE mytable.myid = :mytable_myid AND mytable.name = :mytable_name AND myothertable.othername = :myothertable_othername AND sysdate() = today()"
        )

    def testor(self):
        self.runtest(
            select([table1], and_(
                table1.c.myid == 12,
                or_(table2.c.othername=='asdf', table2.c.othername == 'foo', table2.c.otherid == 9),
                "sysdate() = today()", 
            )),
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = :mytable_myid AND (myothertable.othername = :myothertable_othername OR myothertable.othername = :myothertable_otherna_1 OR myothertable.otherid = :myothertable_otherid) AND sysdate() = today()",
            checkparams = {'myothertable_othername': 'asdf', 'myothertable_otherna_1':'foo', 'myothertable_otherid': 9, 'mytable_myid': 12}
        )

    def testoperators(self):
        self.runtest(
            table1.select((table1.c.myid != 12) & ~(table1.c.name=='john')), 
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid != :mytable_myid AND NOT (mytable.name = :mytable_name)"
        )
        
        self.runtest(
            literal("a") + literal("b") * literal("c"), ":literal + (:liter_1 * :liter_2)", db
        )

    def testmultiparam(self):
        self.runtest(
            select(["*"], or_(table1.c.myid == 12, table1.c.myid=='asdf', table1.c.myid == 'foo')), 
            "SELECT * FROM mytable WHERE mytable.myid = :mytable_myid OR mytable.myid = :mytable_my_1 OR mytable.myid = :mytable_my_2"
        )

    def testorderby(self):
        self.runtest(
            table2.select(order_by = [table2.c.otherid, asc(table2.c.othername)]),
            "SELECT myothertable.otherid, myothertable.othername FROM myothertable ORDER BY myothertable.otherid, myothertable.othername ASC"
        )
    def testgroupby(self):
        self.runtest(
            select([table2.c.othername, func.count(table2.c.otherid)], group_by = [table2.c.othername]),
            "SELECT myothertable.othername, count(myothertable.otherid) FROM myothertable GROUP BY myothertable.othername"
        )

    def testoraclelimit(self):
        e = create_engine('oracle')
        users = Table('users', e, Column('name', String(10), key='username'))
        self.runtest(select([users.c.username], limit=5), "SELECT name FROM (SELECT users.name AS name, ROW_NUMBER() OVER (ORDER BY users.rowid ASC) AS ora_rn FROM users) WHERE ora_rn<=5", engine=e)

    def testgroupby_and_orderby(self):
        self.runtest(
            select([table2.c.othername, func.count(table2.c.otherid)], group_by = [table2.c.othername], order_by = [table2.c.othername]),
            "SELECT myothertable.othername, count(myothertable.otherid) FROM myothertable GROUP BY myothertable.othername ORDER BY myothertable.othername"
        )
    
    def testforupdate(self):
        self.runtest(
            table1.select(table1.c.myid==7, for_update=True), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = :mytable_myid FOR UPDATE"
        )
    def testalias(self):
        # test the alias for a table1.  column names stay the same, table name "changes" to "foo".
        self.runtest(
        select([alias(table1, 'foo')])
        ,"SELECT foo.myid, foo.name, foo.description FROM mytable AS foo")
    
        # create a select for a join of two tables.  use_labels means the column names will have
        # labels tablename_columnname, which become the column keys accessible off the Selectable object.
        # also, only use one column from the second table and all columns from the first table1.
        q = select([table1, table2.c.otherid], table1.c.myid == table2.c.otherid, use_labels = True)
        
        # make an alias of the "selectable".  column names stay the same (i.e. the labels), table name "changes" to "t2view".
        a = alias(q, 't2view')

        # select from that alias, also using labels.  two levels of labels should produce two underscores.
        # also, reference the column "mytable_myid" off of the t2view alias.
        self.runtest(
            a.select(a.c.mytable_myid == 9, use_labels = True),
            "SELECT t2view.mytable_myid AS t2view_mytable_myid, t2view.mytable_name AS t2view_mytable_name, \
t2view.mytable_description AS t2view_mytable_description, t2view.myothertable_otherid AS t2view_myothertable_otherid FROM \
(SELECT mytable.myid AS mytable_myid, mytable.name AS mytable_name, mytable.description AS mytable_description, \
myothertable.otherid AS myothertable_otherid FROM mytable, myothertable \
WHERE mytable.myid = myothertable.otherid) AS t2view WHERE t2view.mytable_myid = :t2view_mytable_myid"
        )
        
    def testtext(self):
        self.runtest(
            text("select * from foo where lala = bar") ,
            "select * from foo where lala = bar",
            engine = db
        )

        self.runtest(select(
            ["foobar(a)", "pk_foo_bar(syslaal)"],
            "a = 12",
            from_obj = ["foobar left outer join lala on foobar.foo = lala.foo"],
            engine = db
        ), 
        "SELECT foobar(a), pk_foo_bar(syslaal) FROM foobar left outer join lala on foobar.foo = lala.foo WHERE a = 12")

        # test building a select query programmatically with text
        s = select()
        s.append_column("column1")
        s.append_column("column2")
        s.append_whereclause("column1=12")
        s.append_whereclause("column2=19")
        s.order_by("column1")
        s.append_from("table1")
        self.runtest(s, "SELECT column1, column2 FROM table1 WHERE column1=12 AND column2=19 ORDER BY column1", db)

    def testtextbinds(self):
        self.runtest(
            db.text("select * from foo where lala=:bar and hoho=:whee"), 
                "select * from foo where lala=:bar and hoho=:whee", 
                checkparams={'bar':4, 'whee': 7},
                params={'bar':4, 'whee': 7, 'hoho':10},
                engine=db
        )
        
        engine = postgres.engine({})
        self.runtest(
            engine.text("select * from foo where lala=:bar and hoho=:whee"), 
                "select * from foo where lala=%(bar)s and hoho=%(whee)s", 
                checkparams={'bar':4, 'whee': 7},
                params={'bar':4, 'whee': 7, 'hoho':10},
                engine=engine
        )

        engine = sqlite.engine({})
        self.runtest(
            engine.text("select * from foo where lala=:bar and hoho=:whee"), 
                "select * from foo where lala=? and hoho=?", 
                checkparams=[4, 7],
                params={'bar':4, 'whee': 7, 'hoho':10},
                engine=engine
        )
        
    def testtextmix(self):
        self.runtest(select(
            [table1, table2.c.otherid, "sysdate()", "foo, bar, lala"],
            and_(
                "foo.id = foofoo(lala)",
                "datetime(foo) = Today",
                table1.c.myid == table2.c.otherid,
            )
        ), 
        "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, sysdate(), foo, bar, lala \
FROM mytable, myothertable WHERE foo.id = foofoo(lala) AND datetime(foo) = Today AND mytable.myid = myothertable.otherid")

    def testtextualsubquery(self):
        self.runtest(select(
            [alias(table1, 't'), "foo.f"],
            "foo.f = t.id",
            from_obj = ["(select f from bar where lala=heyhey) foo"]
        ), 
        "SELECT t.myid, t.name, t.description, foo.f FROM mytable AS t, (select f from bar where lala=heyhey) foo WHERE foo.f = t.id")

    def testliteral(self):
        self.runtest(select([literal("foo") + literal("bar")], from_obj=[table1]), 
            "SELECT :literal + :liter_1 FROM mytable")

    def testcalculatedcolumns(self):
         value_tbl = table('values',
             Column('id', Integer),
             Column('val1', Float),
             Column('val2', Float),
         )

         self.runtest(
             select([value_tbl.c.id, (value_tbl.c.val2 -
     value_tbl.c.val1)/value_tbl.c.val1]),
             "SELECT values.id, (values.val2 - values.val1) / values.val1 FROM values"
         )

         self.runtest(
             select([value_tbl.c.id], (value_tbl.c.val2 -
     value_tbl.c.val1)/value_tbl.c.val1 > 2.0),
             "SELECT values.id FROM values WHERE ((values.val2 - values.val1) / values.val1) > :literal"
         )

         self.runtest(
             select([value_tbl.c.id], value_tbl.c.val1 / (value_tbl.c.val2 - value_tbl.c.val1) /value_tbl.c.val1 > 2.0),
             "SELECT values.id FROM values WHERE ((values.val1 / (values.val2 - values.val1)) / values.val1) > :literal"
         )
         
    def testfunction(self):
        """tests the generation of functions using the func keyword"""
        # test an expression with a function
        self.runtest(func.lala(3, 4, literal("five"), table1.c.myid) * table2.c.otherid, 
            "lala(:lala, :la_1, :literal, mytable.myid) * myothertable.otherid")

        # test it in a SELECT
        self.runtest(select([func.count(table1.c.myid)]), 
            "SELECT count(mytable.myid) FROM mytable")

        # test a "dotted" function name
        self.runtest(select([func.foo.bar.lala(table1.c.myid)]), 
            "SELECT foo.bar.lala(mytable.myid) FROM mytable")

        # test the bind parameter name with a "dotted" function name is only the name
        # (limits the length of the bind param name)
        self.runtest(select([func.foo.bar.lala(12)]), 
            "SELECT foo.bar.lala(:lala)")

        # test a dotted func off the engine itself
        self.runtest(db.func.lala.hoho(7), "lala.hoho(:hoho)")
        
    def testjoin(self):
        self.runtest(
            join(table2, table1, table1.c.myid == table2.c.otherid).select(),
            "SELECT myothertable.otherid, myothertable.othername, mytable.myid, mytable.name, \
mytable.description FROM myothertable JOIN mytable ON mytable.myid = myothertable.otherid"
        )

        self.runtest(
            select(
             [table1],
                from_obj = [join(table1, table2, table1.c.myid == table2.c.otherid)]
            ),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable JOIN myothertable ON mytable.myid = myothertable.otherid")

        self.runtest(
            select(
                [join(join(table1, table2, table1.c.myid == table2.c.otherid), table3, table1.c.myid == table3.c.userid)
            ]),
            "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername, thirdtable.userid, thirdtable.otherstuff FROM mytable JOIN myothertable ON mytable.myid = myothertable.otherid JOIN thirdtable ON mytable.myid = thirdtable.userid"
        )
        
        self.runtest(
            join(users, addresses, users.c.user_id==addresses.c.user_id).select(),
            "SELECT users.user_id, users.user_name, users.password, addresses.address_id, addresses.user_id, addresses.street, addresses.city, addresses.state, addresses.zip FROM users JOIN addresses ON users.user_id = addresses.user_id"
        )
        
    def testmultijoin(self):
        self.runtest(
                select([table1, table2, table3],
                
                from_obj = [join(table1, table2, table1.c.myid == table2.c.otherid).outerjoin(table3, table1.c.myid==table3.c.userid)]
                
                #from_obj = [outerjoin(join(table, table2, table1.c.myid == table2.c.otherid), table3, table1.c.myid==table3.c.userid)]
                )
                ,"SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername, thirdtable.userid, thirdtable.otherstuff FROM mytable JOIN myothertable ON mytable.myid = myothertable.otherid LEFT OUTER JOIN thirdtable ON mytable.myid = thirdtable.userid"
            )
        self.runtest(
                select([table1, table2, table3],
                from_obj = [outerjoin(table1, join(table2, table3, table2.c.otherid == table3.c.userid), table1.c.myid==table2.c.otherid)]
                )
                ,"SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername, thirdtable.userid, thirdtable.otherstuff FROM mytable LEFT OUTER JOIN (myothertable JOIN thirdtable ON myothertable.otherid = thirdtable.userid) ON mytable.myid = myothertable.otherid"
            )
            
    def testunion(self):
            x = union(
                  select([table1], table1.c.myid == 5),
                  select([table1], table1.c.myid == 12),
                  order_by = [table1.c.myid],
            )
  
            self.runtest(x, "SELECT mytable.myid, mytable.name, mytable.description \
FROM mytable WHERE mytable.myid = :mytable_myid UNION \
SELECT mytable.myid, mytable.name, mytable.description \
FROM mytable WHERE mytable.myid = :mytable_my_1 ORDER BY mytable.myid")
  
            self.runtest(
                    union(
                        select([table1]),
                        select([table2]),
                        select([table3])
                    )
            ,
            "SELECT mytable.myid, mytable.name, mytable.description \
FROM mytable UNION SELECT myothertable.otherid, myothertable.othername \
FROM myothertable UNION SELECT thirdtable.userid, thirdtable.otherstuff FROM thirdtable")
            
            
    def testouterjoin(self):
        # test an outer join.  the oracle module should take the ON clause of the join and
        # move it up to the WHERE clause of its parent select, and append (+) to all right-hand-side columns
        # within the original onclause, but leave right-hand-side columns unchanged outside of the onclause
        # parameters.
        
        query = select(
                [table1, table2],
                and_(
                    table1.c.name == 'fred',
                    table1.c.myid == 10,
                    table2.c.othername != 'jack',
                    "EXISTS (select yay from foo where boo = lar)"
                ),
                from_obj = [ outerjoin(table1, table2, table1.c.myid == table2.c.otherid) ]
                )
                
        self.runtest(query, 
            "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername \
FROM mytable LEFT OUTER JOIN myothertable ON mytable.myid = myothertable.otherid \
WHERE mytable.name = %(mytable_name)s AND mytable.myid = %(mytable_myid)s AND \
myothertable.othername != %(myothertable_othername)s AND \
EXISTS (select yay from foo where boo = lar)",
            engine = postgres.engine({}))


        self.runtest(query, 
            "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername \
FROM mytable, myothertable WHERE mytable.myid = myothertable.otherid(+) AND \
mytable.name = :mytable_name AND mytable.myid = :mytable_myid AND \
myothertable.othername != :myothertable_othername AND EXISTS (select yay from foo where boo = lar)",
            engine = oracle.engine({}, use_ansi = False))

        query = table1.outerjoin(table2, table1.c.myid==table2.c.otherid).outerjoin(table3, table3.c.userid==table2.c.otherid)
        self.runtest(query.select(), "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername, thirdtable.userid, thirdtable.otherstuff FROM mytable LEFT OUTER JOIN myothertable ON mytable.myid = myothertable.otherid LEFT OUTER JOIN thirdtable ON thirdtable.userid = myothertable.otherid")
        self.runtest(query.select(), "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername, thirdtable.userid, thirdtable.otherstuff FROM mytable, myothertable, thirdtable WHERE mytable.myid = myothertable.otherid(+) AND thirdtable.userid(+) = myothertable.otherid", engine=oracle.engine({}, use_ansi=False))    

    def testbindparam(self):
        self.runtest(select(
                    [table1, table2],
                    and_(table1.c.myid == table2.c.otherid,
                    table1.c.name == bindparam('mytablename'),
                    )
                ),
                "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername \
FROM mytable, myothertable WHERE mytable.myid = myothertable.otherid AND mytable.name = :mytablename"
                )

        # check that the bind params sent along with a compile() call
        # get preserved when the params are retreived later
        s = select([table1], table1.c.myid == bindparam('test'))
        c = s.compile(parameters = {'test' : 7}, engine=db)
        self.assert_(c.get_params() == {'test' : 7})


    def testin(self):
        self.runtest(select([table1], table1.c.myid.in_(1, 2, 3)),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid, :mytable_my_1, :mytable_my_2)")

        self.runtest(select([table1], table1.c.myid.in_(select([table2.c.otherid]))),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (SELECT myothertable.otherid AS otherid FROM myothertable)")
    
    def testlateargs(self):
        """tests that a SELECT clause will have extra "WHERE" clauses added to it at compile time if extra arguments
        are sent"""
        
        self.runtest(table1.select(), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.name = :mytable_name AND mytable.myid = :mytable_myid", params={'myid':'3', 'name':'jack'})

        self.runtest(table1.select(table1.c.name=='jack'), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = :mytable_myid AND mytable.name = :mytable_name", params={'myid':'3'})

        self.runtest(table1.select(table1.c.name=='jack'), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = :mytable_myid AND mytable.name = :mytable_name", params={'myid':'3', 'name':'fred'})
        
    def testcast(self):
        tbl = table('casttest',
                    Column('id', Integer),
                    Column('v1', Float),
                    Column('v2', Float),
                    Column('ts', TIMESTAMP),
                    )
        
        def check_results(engine, expected_results, literal):
            self.assertEqual(len(expected_results), 5, 'Incorrect number of expected results')
            self.assertEqual(str(cast(tbl.c.v1, Numeric, engine=engine)), 'CAST(casttest.v1 AS %s)' %expected_results[0])
            self.assertEqual(str(cast(tbl.c.v1, Numeric(12, 9), engine=engine)), 'CAST(casttest.v1 AS %s)' %expected_results[1])
            self.assertEqual(str(cast(tbl.c.ts, Date, engine=engine)), 'CAST(casttest.ts AS %s)' %expected_results[2])
            self.assertEqual(str(cast(1234, TEXT, engine=engine)), 'CAST(%s AS %s)' %(literal, expected_results[3]))
            self.assertEqual(str(cast('test', String(20), engine=engine)), 'CAST(%s AS %s)' %(literal, expected_results[4]))
            
            sel = select([tbl, cast(tbl.c.v1, Numeric)], engine=engine)
            self.assertEqual(str(sel), "SELECT casttest.id, casttest.v1, casttest.v2, casttest.ts, CAST(casttest.v1 AS NUMERIC(10, 2)) \nFROM casttest")
            
        # first test with Postgres engine
        check_results(postgres.engine({}), ['NUMERIC(10, 2)', 'NUMERIC(12, 9)', 'DATE', 'TEXT', 'VARCHAR(20)'], '%(literal)s')

        # then the Oracle engine
        check_results(oracle.engine({}, use_ansi = False), ['NUMERIC(10, 2)', 'NUMERIC(12, 9)', 'DATE', 'CLOB', 'VARCHAR(20)'], ':literal')

        # then the sqlite engine
        check_results(sqlite.engine({}), ['NUMERIC(10, 2)', 'NUMERIC(12, 9)', 'DATE', 'TEXT', 'VARCHAR(20)'], '?')

        # and the MySQL engine
        check_results(mysql.engine({}), ['NUMERIC(10, 2)', 'NUMERIC(12, 9)', 'DATE', 'TEXT', 'VARCHAR(20)'], '%s')

class CRUDTest(SQLTest):
    def testinsert(self):
        # generic insert, will create bind params for all columns
        self.runtest(insert(table1), "INSERT INTO mytable (myid, name, description) VALUES (:myid, :name, :description)")

        # insert with user-supplied bind params for specific columns,
        # cols provided literally
        self.runtest(
            insert(table1, {table1.c.myid : bindparam('userid'), table1.c.name : bindparam('username')}), 
            "INSERT INTO mytable (myid, name) VALUES (:userid, :username)")
        
        # insert with user-supplied bind params for specific columns, cols
        # provided as strings
        self.runtest(
            insert(table1, dict(myid = 3, name = 'jack')), 
            "INSERT INTO mytable (myid, name) VALUES (:myid, :name)"
        )

        # test with a tuple of params instead of named
        self.runtest(
            insert(table1, (3, 'jack', 'mydescription')), 
            "INSERT INTO mytable (myid, name, description) VALUES (:myid, :name, :description)",
            checkparams = {'myid':3, 'name':'jack', 'description':'mydescription'}
        )
    
    def testinsertexpression(self):
        self.runtest(insert(table1), "INSERT INTO mytable (myid) VALUES (lala())", params=dict(myid=func.lala()))
        
    def testupdate(self):
        self.runtest(update(table1, table1.c.myid == 7), "UPDATE mytable SET name=:name WHERE mytable.myid = :mytable_myid", params = {table1.c.name:'fred'})
        self.runtest(update(table1, table1.c.myid == 7), "UPDATE mytable SET name=:name WHERE mytable.myid = :mytable_myid", params = {'name':'fred'})
        self.runtest(update(table1, values = {table1.c.name : table1.c.myid}), "UPDATE mytable SET name=mytable.myid")
        self.runtest(update(table1, whereclause = table1.c.name == bindparam('crit'), values = {table1.c.name : 'hi'}), "UPDATE mytable SET name=:name WHERE mytable.name = :crit", params = {'crit' : 'notthere'})
        self.runtest(update(table1, table1.c.myid == 12, values = {table1.c.name : table1.c.myid}), "UPDATE mytable SET name=mytable.myid, description=:description WHERE mytable.myid = :mytable_myid", params = {'description':'test'})
        self.runtest(update(table1, table1.c.myid == 12, values = {table1.c.myid : 9}), "UPDATE mytable SET myid=:myid, description=:description WHERE mytable.myid = :mytable_myid", params = {'mytable_myid': 12, 'myid': 9, 'description': 'test'})
        s = table1.update(table1.c.myid == 12, values = {table1.c.name : 'lala'})
        c = s.compile(parameters = {'mytable_id':9,'name':'h0h0'}, engine=db)
        print str(c)
        self.assert_(str(s) == str(c))
        
    def testupdateexpression(self):
        self.runtest(update(table1, 
            (table1.c.myid == func.hoho(4)) &
            (table1.c.name == literal('foo') + table1.c.name + literal('lala')),
            values = {
            table1.c.name : table1.c.name + "lala",
            table1.c.myid : func.do_stuff(table1.c.myid, literal('hoho'))
            }), "UPDATE mytable SET myid=do_stuff(mytable.myid, :liter_2), name=mytable.name + :mytable_name WHERE mytable.myid = hoho(:hoho) AND mytable.name = ((:literal + mytable.name) + :liter_1)")
        
    def testcorrelatedupdate(self):
        # test against a straight text subquery
        u = update(table1, values = {table1.c.name : text("select name from mytable where id=mytable.id")})
        self.runtest(u, "UPDATE mytable SET name=(select name from mytable where id=mytable.id)")
        
        # test against a regular constructed subquery
        s = select([table2], table2.c.otherid == table1.c.myid)
        u = update(table1, table1.c.name == 'jack', values = {table1.c.name : s})
        self.runtest(u, "UPDATE mytable SET name=(SELECT myothertable.otherid, myothertable.othername FROM myothertable WHERE myothertable.otherid = mytable.myid) WHERE mytable.name = :mytable_name")
        
        # test a correlated WHERE clause
        s = select([table2.c.othername], table2.c.otherid == 7)
        u = update(table1, table1.c.name==s)
        self.runtest(u, "UPDATE mytable SET myid=:myid, name=:name, description=:description WHERE mytable.name = (SELECT myothertable.othername FROM myothertable WHERE myothertable.otherid = :myothertable_otherid)")
        
    def testdelete(self):
        self.runtest(delete(table1, table1.c.myid == 7), "DELETE FROM mytable WHERE mytable.myid = :mytable_myid")
        
class SchemaTest(SQLTest):
    def testselect(self):
        # these tests will fail with the MS-SQL compiler since it will alias schema-qualified tables
        self.runtest(table4.select(), "SELECT remotetable.rem_id, remotetable.datatype_id, remotetable.value FROM remote_owner.remotetable")
        self.runtest(table4.select(and_(table4.c.datatype_id==7, table4.c.value=='hi')), "SELECT remotetable.rem_id, remotetable.datatype_id, remotetable.value FROM remote_owner.remotetable WHERE remotetable.datatype_id = :remotetable_datatype_id AND remotetable.value = :remotetable_value")

        s = table4.select(and_(table4.c.datatype_id==7, table4.c.value=='hi'))
        s.use_labels = True
        self.runtest(s, "SELECT remotetable.rem_id AS remotetable_rem_id, remotetable.datatype_id AS remotetable_datatype_id, remotetable.value AS remotetable_value FROM remote_owner.remotetable WHERE remotetable.datatype_id = :remotetable_datatype_id AND remotetable.value = :remotetable_value")

    def testalias(self):
        a = alias(table4, 'remtable')
        self.runtest(a.select(a.c.datatype_id==7), "SELECT remtable.rem_id, remtable.datatype_id, remtable.value FROM remote_owner.remotetable AS remtable WHERE remtable.datatype_id = :remtable_datatype_id")
        
    def testupdate(self):
        self.runtest(table4.update(table4.c.value=='test', values={table4.c.datatype_id:12}), "UPDATE remote_owner.remotetable SET datatype_id=:datatype_id WHERE remotetable.value = :remotetable_value")
        
    def testinsert(self):
        self.runtest(table4.insert(values=(2, 5, 'test')), "INSERT INTO remote_owner.remotetable (rem_id, datatype_id, value) VALUES (:rem_id, :datatype_id, :value)")
        
if __name__ == "__main__":
    unittest.main()        