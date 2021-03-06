import ast
import logging
import sqlalchemy as sa
from sqlalchemy.sql import dml
from sqlalchemy.sql.expression import bindparam
from typing import Union, List, Set


filter_list_type = Union[List[str], Set[str], None]

LOGGER = logging.getLogger(__package__)
POSTGRE_TO_MYSQL = {}
UPDATE_NOT_VALUES = TypeError("update not has values")


def return_true(*args):
    return True


def get_filter_list(
        block_list: filter_list_type=None,
        white_list: filter_list_type=None
        ):
    """
    生成过滤黑白名单
    """
    if not block_list and not white_list:
        return return_true
    if block_list and isinstance(block_list, list):
        block_list = set(block_list)
    if white_list and isinstance(white_list, list):
        white_list = set(white_list)

    def filter_list(key: str) -> bool:
        """
        过滤黑白名单
        """
        status = True
        if block_list:
            status &= key not in block_list
        if white_list:
            status &= key in white_list
        return status
    return filter_list


def handle_param(column, data):
    """
    处理where条件
    """
    opt = data.get('opt', '$te')
    if 'val' in data:
        value = data['val']
        if opt == '$ne':  # 不等于
            return column != value
        if opt == '$te':  # 等于
            return column == value
        elif opt == '$lt':  # 小于
            return column < value
        elif opt == '$lte':  # 小于等于
            return column <= value
        elif opt == '$gt':  # 大于
            return column > value
        elif opt == '$gte':  # 大于等于
            return column >= value
        elif opt == '$like':  # like
            return column.like(value)
        elif opt == '$in':
            return column.in_(value)
        elif opt == '$nin':
            return ~column.in_(value)
        # elif opt == "$day":
        #     column = sa.extract("day", column)
        #     return handle_param(column, value)
        # elif opt == "$month":
        #     column = sa.extract("month", column)
        #     return handle_param(column, value)
        # elif opt == "$year":
        #     column = sa.extract("year", column)
        #     return handle_param(column, value)
        elif opt == '$bind':
            # 占位符
            if isinstance(value, str):
                return column == bindparam(value)
            else:
                opt = value["opt"]
                if opt == '$bind':
                    return None
                if opt == "$in" or opt == "$nin":
                    value["val"] = bindparam(value["val"], expanding=True)
                else:
                    value["val"] = bindparam(value["val"])
                return handle_param(column, value)
        elif opt == '$raw':
            return value


def handle_param_desc(column, data):
    """
    处理参数类型
    """
    params = []
    if isinstance(data, list):
        if len(data) > 0:
            for row in data:
                param = handle_param(column, row)
                if param is not None:
                    params.append(param)
    elif isinstance(data, dict):
        param = handle_param(column, data)
        if param is not None:
            params.append(param)
    else:
        params.append(column == data)
    # 结合为一个 where 参数
    params_len = len(params)
    if params_len == 1:
        return params[0]
    elif params_len > 1:
        return sa.and_(*params)


def handle_where_param(
        column_name,
        form_data,
        filter_list=return_true,
        is_or=False
        ):
    """
    处理带主键的参数
    """
    if form_data is None:
        return
    data = []
    for key, val in form_data.items():
        if key == "$or" or key == "$and":
            # 递归处理新的where, 让 or 内部支持 and 嵌套
            params = handle_where_param(
                column_name,
                val,
                filter_list,
                key == "$or"
            )
            if params is not None:
                data.append(params)
        elif key in column_name and filter_list(key):
            # 在表中且不被名单过滤
            column = column_name[key]
            # 将 value 处理
            params = handle_param_desc(column, val)
            if params is not None:
                data.append(params)
    data_len = len(data)
    # 结合为一个 where 参数
    if data_len == 1:
        return data[0]
    elif data_len > 1:
        return sa.or_(*data) if is_or else sa.and_(*data)


def inject_value(value: str, cache):
    arr = value[1:].split(".")
    table = arr[0]
    if len(arr) == 3:
        index = int(arr[1])
        field = arr[2]
    else:
        index = 0
        field = arr[1]
    if table in cache:
        table_cache = cache[table]
        if isinstance(table_cache, list):
            if field in table_cache[index]:
                return table_cache[index][field]
        elif field in table_cache:
            return table_cache[field]
    return value


def insert_sql(model: sa.Table, data, filter_list=return_true) -> dml.Insert:
    """
    生成插入语句对象
    """
    if isinstance(data, list):
        data = [{k: v for k, v in m.items() if filter_list(k)} for m in data]
    else:
        data = {k: v for k, v in data.items() if filter_list(k)}
    return model.insert().values(data)


def delete_sql(model: sa.Table, data, filter_list=return_true) -> dml.Delete:
    """
    生成删除语句对象
    """
    where_data = handle_where_param(model.columns, data, filter_list)
    if where_data is not None:
        return model.delete().where(where_data)
    return model.delete()


def update_sql(
            model: sa.Table,
            data,
            filter_list=return_true,
            where_filter=return_true
        ) -> dml.Update:
    """
    生成更新语句对象
    """
    if isinstance(data, list):
        res = []
        for d in data:
            res.append(update_sql(model, d, filter_list))
        return res
    where = data.get("where")
    where_data = handle_where_param(model.columns, where, where_filter)
    values = data.get("values")
    if values is None:
        raise UPDATE_NOT_VALUES
    values_data = {}
    for key, val in values.items():
        if key in model.columns and filter_list(key):
            if isinstance(val, str):
                if val.startswith("$bind."):
                    values_data[key] = bindparam(val[6:])
                elif val.startswith("$incr."):
                    incr = int(val[6:])
                    column = getattr(model.columns, key)
                    if incr > 0:
                        values_data[key] = column + incr
                    elif incr < 0:
                        values_data[key] = column - (-incr)
                else:
                    values_data[key] = val
            else:
                values_data[key] = val
    if where_data is not None:
        sql = model.update().where(where_data)
    else:
        sql = model.update()
    if len(values_data) == 0:
        raise UPDATE_NOT_VALUES
    return sql.values(values_data)


def handle_orders(columns, orders, filter_list):
    """
    处理排序
    """
    order_by = []
    for order in orders:
        is_desc = False
        if order[0] == "-":
            order = order[1:]
            is_desc = True
        if order in columns and filter_list(order):
            column = columns[order]
            if is_desc:
                order_by.append(sa.desc(column))
            else:
                order_by.append(column)
        elif order not in columns:
            order_by.append(sa.desc(order) if is_desc else order)
    if len(order_by) > 0:
        return order_by


def handle_func_args(columns, args, filter_list):
    argv = []
    flag = False
    for arg in args:
        if isinstance(arg, str) and arg[0] == "$":
            if arg[1] == "$":
                argv.append(arg[1:])
                continue
            column_name = arg[1:]
            if column_name in columns and filter_list(column_name):
                column = columns[column_name]
                argv.append(column)
                flag = True
        else:
            argv.append(arg)
    if flag:
        return argv


def handle_keys(columns, keys, filter_list, drivername):
    res = []
    for key in keys:
        if isinstance(key, dict):
            func_name = key.get("func")
            label = key.get("label")
            args = key.get("args")
            column_name = key.get("column")
            if column_name in columns and filter_list(column_name):
                column = columns[column_name]
                # if drivername == "sqlite":
                #     if func_name == "from_unixtime":
                #         func_name = "strftime"
                #         format_str = args[0].replace(r"%i", r"%M")
                #         args = [format_str, "$column", "unixepoch"]
                #     elif func_name == "date_format":
                #         func_name = "strftime"
                #         format_str = args[0].replace(r"%i", r"%M")
                #         args = [format_str, "$column"]
                # elif drivername == "postgresql":
                #     if func_name == "from_unixtime":
                #         func_name = "to_char"

                if func_name and hasattr(sa.func, func_name):
                    func = getattr(sa.func, func_name)
                    if args:
                        if "$column" in args:
                            arg = []
                            for s in args:
                                if s == "$column":
                                    arg.append(column)
                                else:
                                    arg.append(s)
                            temp = func(*arg)
                        else:
                            temp = func(column, *args)
                    else:
                        temp = func(column)
                    column = temp
                if label:
                    column = column.label(label)
                res.append(column)
        elif isinstance(key, str):
            column = None
            label = None
            label_start = key.rfind("):")
            if label_start > -1:
                label = key[label_start+2:].strip()
                key = key[:label_start+1]
            start = key.find("(")
            if start > 0:
                func_name = key[:start].strip()
                end = key.rfind(")")
                args_str = ast.literal_eval(key[start: end+1])
                args = handle_func_args(
                    columns,
                    args_str,
                    filter_list,
                )
                if args is not None and hasattr(sa.func, func_name):
                    func = getattr(sa.func, func_name)
                    column = func(*args)
                else:
                    LOGGER.warn("not parse key: %s" % key)
                    continue
            if column is None and key in columns and filter_list(key):
                column = columns[key]
            if column is not None:
                if label is not None:
                    column = column.label(label)
                res.append(column)
        else:
            LOGGER.warn("utils.handle_keys: `%s` key not is str or dict", key)
    return res


def select_sql(
    model: sa.Table,
    data,
    filter_list=return_true,
    keys=None,
    orders=None,
    limit=None,
    group=None,
    drivername=None
):
    """
    生成查询语句对象
    """
    where_data = handle_where_param(model.columns, data, filter_list)
    if keys:
        columns = handle_keys(model.columns, keys, filter_list, drivername)
    else:
        columns = [
            column for column in model.columns if filter_list(column.name)
        ]
    sql = sa.sql.select(columns)
    if where_data is not None:
        sql = sql.where(where_data)
    if group:
        group_by = []
        for g in group:
            if g in model.columns and filter_list(g):
                group_by.append(model.columns[g])
            elif g not in model.columns:
                group_by.append(g)
        if len(group_by) > 0:
            sql = sql.group_by(*group_by)
    if orders:
        order_by = handle_orders(model.columns, orders, filter_list)
        if order_by:
            sql = sql.order_by(*order_by)
    if limit:
        for c in model.columns:
            column = c
            break
        offset_num, limit_num = limit
        sql = sql.offset(offset_num).limit(limit_num)
        sql_count = sa.sql.select([sa.func.count(column).label("_count")])
        if where_data is not None:
            sql_count = sql_count.where(where_data)
        return sql, sql_count
    return sql


def model_to_dict(row):
    """
    把model查询出的row转换为dict
    """
    return {key: val for key, val in row.items()}
