package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;
import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.Reader;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class ExtendedBufferedReader_3_5Test {

    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        Reader mockReader = Mockito.mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testReadAgain_initialUndefined() throws Exception {
        setLastChar(ExtendedBufferedReader.UNDEFINED);
        int result = invokeReadAgain();
        assertEquals(ExtendedBufferedReader.UNDEFINED, result);
    }

    @Test
    @Timeout(8000)
    void testReadAgain_withEndOfStream() throws Exception {
        setLastChar(ExtendedBufferedReader.END_OF_STREAM);
        int result = invokeReadAgain();
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, result);
    }

    @Test
    @Timeout(8000)
    void testReadAgain_withPositiveChar() throws Exception {
        setLastChar(65);
        int result = invokeReadAgain();
        assertEquals(65, result);
    }

    private void setLastChar(int value) throws Exception {
        Field field = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        field.setAccessible(true);
        field.setInt(extendedBufferedReader, value);
    }

    private int invokeReadAgain() throws Exception {
        Method method = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        method.setAccessible(true);
        return (int) method.invoke(extendedBufferedReader);
    }
}