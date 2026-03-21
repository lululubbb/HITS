package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import java.io.IOException;
import java.io.Reader;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class ExtendedBufferedReader_4_2Test {

    private ExtendedBufferedReader readerSpy;

    @BeforeEach
    void setUp() {
        Reader mockReader = mock(Reader.class);
        readerSpy = Mockito.spy(new ExtendedBufferedReader(mockReader));
    }

    @Test
    @Timeout(8000)
    void testRead_lengthZero_returnsZero() throws IOException {
        char[] buf = new char[10];
        int result = readerSpy.read(buf, 0, 0);
        assertEquals(0, result);
        verify(readerSpy, never()).read(any(char[].class), anyInt(), anyInt());
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_noNewlineOrCarriageReturn() throws IOException {
        char[] buf = new char[10];
        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            b[off] = 'a';
            b[off + 1] = 'b';
            b[off + 2] = 'c';
            return 3;
        }).when(readerSpy).read(any(char[].class), anyInt(), anyInt());

        int result = readerSpy.read(buf, 1, 3);
        assertEquals(3, result);
        assertEquals((int) 'c', (int) getPrivateField(readerSpy, "lastChar"));
        assertEquals(0, (int) getPrivateField(readerSpy, "lineCounter"));
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_withNewlinesAndCarriageReturns() throws IOException {
        char[] buf = new char[10];
        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            b[off] = 'a';
            b[off + 1] = '\n';
            b[off + 2] = '\n';
            b[off + 3] = '\r';
            b[off + 4] = '\n';
            return 5;
        }).when(readerSpy).read(any(char[].class), anyInt(), anyInt());

        setPrivateField(readerSpy, "lastChar", (int) 'x');
        int result = readerSpy.read(buf, 1, 5);
        assertEquals(5, result);

        assertEquals(3, (int) getPrivateField(readerSpy, "lineCounter"));
        assertEquals((int) '\n', (int) getPrivateField(readerSpy, "lastChar"));
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_withNewlinePrecededByCarriageReturn() throws IOException {
        char[] buf = new char[10];
        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            b[off] = '\r';
            b[off + 1] = '\n';
            b[off + 2] = 'a';
            return 3;
        }).when(readerSpy).read(any(char[].class), anyInt(), anyInt());

        setPrivateField(readerSpy, "lastChar", (int) 'x');
        int result = readerSpy.read(buf, 0, 3);
        assertEquals(3, result);

        assertEquals(1, (int) getPrivateField(readerSpy, "lineCounter"));
        assertEquals((int) 'a', (int) getPrivateField(readerSpy, "lastChar"));
    }

    @Test
    @Timeout(8000)
    void testRead_lenNegativeOne_setsEndOfStream() throws IOException {
        char[] buf = new char[10];
        doReturn(-1).when(readerSpy).read(any(char[].class), anyInt(), anyInt());

        setPrivateField(readerSpy, "lastChar", (int) 'x');
        int result = readerSpy.read(buf, 0, 5);
        assertEquals(-1, result);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, (int) getPrivateField(readerSpy, "lastChar"));
    }

    @SuppressWarnings("unchecked")
    private <T> T getPrivateField(Object instance, String fieldName) {
        try {
            java.lang.reflect.Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            Object val = field.get(instance);
            if (val instanceof Character) {
                return (T) (Integer) Integer.valueOf(((Character) val).charValue());
            }
            if (val instanceof Integer) {
                return (T) val;
            }
            return (T) val;
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private void setPrivateField(Object instance, String fieldName, Object value) {
        try {
            java.lang.reflect.Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            if (field.getType() == int.class && value instanceof Character) {
                field.set(instance, (int) ((Character) value).charValue());
            } else if (field.getType() == int.class && value instanceof Integer) {
                field.set(instance, value);
            } else {
                field.set(instance, value);
            }
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}