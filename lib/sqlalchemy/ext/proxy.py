try:
    from threading import local
except ImportError:
    from sqlalchemy.util import ThreadLocal as local

from sqlalchemy import sql
from sqlalchemy.engine import create_engine
from sqlalchemy.types import TypeEngine
import sqlalchemy.schema as schema
import thread, weakref

class BaseProxyEngine(schema.SchemaEngine):
    '''
    Basis for all proxy engines
    '''
        
    def get_engine(self):
        raise NotImplementedError

    def set_engine(self, engine):
        raise NotImplementedError
        
    engine = property(lambda s:s.get_engine(), lambda s,e:s.set_engine(e))

    def reflecttable(self, table):
        return self.get_engine().reflecttable(table)
    def execute_compiled(self, *args, **kwargs):
        return self.get_engine().execute_compiled(*args, **kwargs)
    def compiler(self, *args, **kwargs):
        return self.get_engine().compiler(*args, **kwargs)
    def schemagenerator(self, *args, **kwargs):
        return self.get_engine().schemagenerator(*args, **kwargs)
    def schemadropper(self, *args, **kwargs):
        return self.get_engine().schemadropper(*args, **kwargs)
            
    def hash_key(self):
        return "%s(%s)" % (self.__class__.__name__, id(self))

    def oid_column_name(self):
        # oid_column should not be requested before the engine is connected.
        # it should ideally only be called at query compilation time.
        e= self.get_engine()
        if e is None:
            return None
        return e.oid_column_name()    
        
    def __getattr__(self, attr):
        # call get_engine() to give subclasses a chance to change
        # connection establishment behavior
        e= self.get_engine()
        if e is not None:
            return getattr(e, attr)
        raise AttributeError('No connection established in ProxyEngine: '
                             ' no access to %s' % attr)

class AutoConnectEngine(BaseProxyEngine):
    '''
    An SQLEngine proxy that automatically connects when necessary.
    '''
    
    def __init__(self, dburi, opts=None, **kwargs):
        BaseProxyEngine.__init__(self)
        self.dburi= dburi
        self.opts= opts
        self.kwargs= kwargs
        self._engine= None
        
    def get_engine(self):
        if self._engine is None:
            if callable(self.dburi):
                dburi= self.dburi()
            else:
                dburi= self.dburi
            self._engine= create_engine( dburi, self.opts, **self.kwargs )
        return self._engine


            
class ProxyEngine(BaseProxyEngine):
    """
    SQLEngine proxy. Supports lazy and late initialization by
    delegating to a real engine (set with connect()), and using proxy
    classes for TypeEngine.
    """

    def __init__(self, **kwargs):
        BaseProxyEngine.__init__(self)
        # create the local storage for uri->engine map and current engine
        self.storage = local()
        self.storage.connection = {}
        self.storage.engine = None
        self.kwargs = kwargs
            
    def connect(self, uri, opts=None, **kwargs):
        """Establish connection to a real engine.
        """
        kw = self.kwargs.copy()
        kw.update(kwargs)
        kwargs = kw
        key = "%s(%s,%s)" % (uri, repr(opts), repr(kwargs))
        try:
            map = self.storage.connection
        except AttributeError:
            self.storage.connection = {}
            self.storage.engine = None
            map = self.storage.connection
        try:
            self.engine = map[key]
        except KeyError:
            map[key] = create_engine(uri, opts, **kwargs)
            self.storage.engine = map[key]
            
    def get_engine(self):
        if self.storage.engine is None:
            raise AttributeError('No connection established')
        return self.storage.engine

    def set_engine(self, engine):
        self.storage.engine = engine
        
