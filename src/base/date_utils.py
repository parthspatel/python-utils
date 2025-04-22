import logging
import time
from functools import partial, update_wrapper

TIME_DURATION_UNITS = (("week", 60 * 60 * 24 * 7), ("day", 60 * 60 * 24), ("hour", 60 * 60), ("min", 60), ("sec", 1))


def pretty_print_duration(seconds):
	if seconds == 0:
		return "inf"
	parts = []
	for unit, div in TIME_DURATION_UNITS:
		amount, seconds = divmod(int(seconds), div)
		int_amount = int(amount)
		if int_amount > 0:
			parts.append(f"{int_amount} {unit}{'' if int_amount == 1 else 's'}")
	return ", ".join(parts)


def default_msg_fx(function_name, duration):
	return f"Function {function_name!r} executed in {duration}"


class _TimeMethod:
	def __init__(self, func, msg_fx=default_msg_fx, log_fx=logging.info):
		update_wrapper(self, func)
		self.func = func
		self.msg_fx = msg_fx
		self.log_fx = log_fx

	def __get__(self, obj, objtype):
		"""Support instance methods."""
		return partial(self.__call__, obj)

	def __call__(self, obj, *args, **kwargs):
		# print('Logic here')
		start_time = time.perf_counter()
		result = self.func(obj, *args, **kwargs)
		end_time = time.perf_counter()
		msg = self.msg_fx(self.func.__name__, pretty_print_duration(end_time - start_time))
		self.log_fx(msg)
		# print(f"Function {func.__name__!r} executed in {pretty_print_duration(end_time - start_time)}")
		return result


def TimeMethod(func=None, msg_fx=default_msg_fx, log_fx=logging.info):
	if func:
		return _TimeMethod(func)

	def wrapper(func):
		return _TimeMethod(func, msg_fx, log_fx)

	return wrapper


time_method = TimeMethod
"""
To use the time_method decorator, you can do the following:
@time_method(msg_fx=lambda _, duration: f"> Done XYZ in {duration}!!!", log_fx=lambda x="": logging.info(x))
"""
